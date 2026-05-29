# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import asyncio
import json
import logging
import os
import shutil
import tempfile
from contextvars import ContextVar
from enum import Enum
from typing import Dict, List

import aiohttp
from datasets import Dataset as HFDataset
from datasets import DatasetDict, exceptions
from datasets import load_dataset as hf_load_dataset
from nmp.common.api.common import URN
from nmp.common.files.deprecated_datastore.datasets import Dataset
from nmp.evaluator.app.datasets.nmp_datasets.exceptions import UnsupportedFileFormatException
from nmp.evaluator.app.datasets.nmp_datasets.hf import download_dataset
from pydantic import AnyUrl

# We use a context variable for the name of the logger to use
logger_var = ContextVar("logger_name")


def get_logger() -> logging.Logger:
    return logging.getLogger(logger_var.get(__name__))


class LoadingMode(str, Enum):
    DATASETS = "datasets"  # load dataset using "datasets" package (with pyarrow)
    SIMPLE = "simple"  # load dataset using JSON / JSONL reading


async def to_dataset(dataset: str | URN | Dataset | None) -> Dataset:
    """
    Convert a dataset into URN format into Dataset structure.
    """
    if isinstance(dataset, Dataset):
        return dataset
    elif isinstance(dataset, URN) or isinstance(dataset, str):
        # entity_store_url = app_config.ENTITY_STORE_URL
        entity_store_url = None
        if entity_store_url is None:
            raise ValueError(f"ENTITY_STORE_URL environment variable is not set, cannot fetch dataset {dataset}")

        async with aiohttp.ClientSession() as session:
            async with session.get(f"{entity_store_url}/v1/datasets/{dataset}") as response:
                response.raise_for_status()
                return Dataset.model_validate(await response.json())
    else:
        raise ValueError(f"Unsupported dataset type: {type(dataset)}")


def extract_path(dataset_files_url: str) -> str:
    """
    Function to extract directory path from files_url.
    """
    parts = dataset_files_url.replace("hf://", "").split("/")
    if parts[0] != "datasets":
        raise ValueError(f"Invalid dataset path: {dataset_files_url}. It does not start with hf://datasets.")
    directory_path = "/".join(parts[1:])
    return directory_path


async def load_dataset(dataset: str | URN | Dataset, loading_mode: LoadingMode = LoadingMode.DATASETS) -> List[Dict]:
    """
    Load a dataset from a URN (string) or a Dataset object.

    Args:
        dataset: The dataset to load.

    Returns:
        (List[Dict]) The list of rows. Each row is an object with a property for each column.
    """
    log = get_logger()
    log.debug(f"Loading dataset {dataset}")
    dataset = await to_dataset(dataset)
    return await _load_hf_dataset(dataset, loading_mode)


async def _load_hf_dataset(dataset: Dataset, loading_mode: LoadingMode) -> List[Dict]:
    """Loads a dataset from the given path.

    Supports loading from a specific file, or from a full dataset / folder.

    Args
        path_or_url: The path to the dataset.
        hf_endpoint: The endpoint to use for the dataset.
        split: The split of the dataset to load.
        limit: The maximum number of items to load.
    """
    log = get_logger()
    path_or_url: str

    files_url = str(dataset.files_url)
    # Supported schemas: file:// and hf://
    if files_url.startswith("file://"):
        # Remove the file:// prefix
        path_or_url = files_url[len("file://") :]
    elif files_url.startswith("hf://"):
        path_or_url = files_url
    else:
        raise ValueError(f"Unsupported files_url schema: {files_url}")

    hf_endpoint = dataset.hf_endpoint
    limit = dataset.limit
    split = dataset.split

    # Make sure we're not dealing with AnyUrl instances
    path_or_url = str(path_or_url)
    hf_endpoint = str(hf_endpoint) if hf_endpoint else None

    # To determine if it's a single file, we check if there's a "." in the last segment
    # TODO: make this more robust by checking explicitly for the file extensions supported by HF datasets library
    is_file = "." in path_or_url.split("/")[-1]
    is_url = "://" in path_or_url

    # To use the `datasets.load_dataset` from HF, we heed to have the file(s) in a single folder
    with tempfile.TemporaryDirectory() as temp_dir:
        # If it's an HF URL, we download the file/dataset otherwise, we copy
        if is_url:
            url = AnyUrl(path_or_url)

            if url.scheme != "hf":
                raise ValueError(
                    f"Invalid URL for dataset ({path_or_url}). "
                    f"The {url.scheme} scheme is not supported. "
                    f"Only 'hf' scheme is currently supported."
                )

            log.debug(f"Downloading dataset {path_or_url} to {temp_dir}")
            # For the token, we put a fake one when using Data Store
            hf_token = "token" if os.environ.get("DATA_STORE_URL") else os.environ.get("HF_TOKEN")
            dataset_path, relative_repo_path = await download_dataset(path_or_url, temp_dir, hf_endpoint, hf_token)

        else:
            # If it's a file, we copy it to the temp dir
            dataset_path = temp_dir
            if is_file:
                relative_repo_path = path_or_url.split("/")[-1]
                shutil.copy(path_or_url, temp_dir)
            else:
                relative_repo_path = None
                shutil.copytree(path_or_url, temp_dir, dirs_exist_ok=True)

        log.debug(f"Loading dataset from {dataset_path}")
        if loading_mode == LoadingMode.DATASETS:
            # Load the dataset; this also involves File IO, so we run in separate thread
            rows = await asyncio.to_thread(
                _load_dataset_with_hf, dataset_path=dataset_path, relative_repo_path=relative_repo_path, split=split
            )
        else:
            rows = await asyncio.to_thread(
                _load_dataset_with_json, dataset_path=dataset_path, relative_repo_path=relative_repo_path
            )
        log.info(f"Loaded dataset from {path_or_url}")

        # Return a maximum of `limit` items
        return rows[:limit]


def _load_dataset_with_hf(dataset_path: str, relative_repo_path: str | None, split: str | None = None) -> list:
    """
    Load content of dataset using hf_load_dataset from directory
    """
    log = get_logger()
    try:
        dataset = hf_load_dataset(path=dataset_path, split=split)

        if isinstance(dataset, DatasetDict):
            dataset = dataset[split or list(dataset.keys())[0]]
            return dataset.to_list()
        else:
            assert isinstance(dataset, HFDataset)
            return dataset.to_list()

    except exceptions.DatasetGenerationError:
        # This branch of code is for cases when the dataset cannot be parsed with 'datasets'
        # because the pyarrow that 'datasets' use in the background is too strict and requires the JSON
        # to conform to a consistent schema (that pyarrow determines on the fly).
        # This particularly breaks for the cases when the args of same names in the tool_calls contain
        # values of different types (eg. some function arg named limit refers to int for one function
        # but float or even string for another) and pyarrow throws exception wrapped into
        # the datasets.exceptions.DatasetGenerationError (eg limit has been used with type X but now with type Y).
        #
        # To work around this restriction - the code switches back to a simplified json/jsonl reading

        log.exception("Error when parsing the dataset. Switching to simplified dataset loading.")
        return _load_dataset_with_json(dataset_path, relative_repo_path)


def _load_dataset_with_json(dataset_path: str, relative_repo_path: str | None) -> list:
    """
    Load content of dataset files using json.load or json.loads from path. `relative_repo_path` can be the
    relative path from dataset_path to a single file or a subdirectory.
    """
    log = get_logger()
    full_contents: list = []

    file_paths = []
    if relative_repo_path:
        full_dataset_path = os.path.join(dataset_path, relative_repo_path)
        if os.path.isfile(full_dataset_path):
            # Single file to read only
            file_paths = [full_dataset_path]
        else:
            # Subdirectory to read
            file_paths = walk_directory_for_files(full_dataset_path)
    else:
        # Whole dataset
        file_paths = walk_directory_for_files(dataset_path)

    for filename in file_paths:
        if os.path.isfile(filename):
            log.debug(f"Reading from {filename}")
            if filename.endswith(".json"):
                full_contents.extend(_read_json(filename))
            elif filename.endswith(".jsonl"):
                full_contents.extend(_read_jsonl(filename))
            else:
                raise UnsupportedFileFormatException(
                    f"Unable to parse the dataset. Files either need to follow strict typing within columns or be in JSON / JSONL format: {dataset_path} {filename}"
                )

    return full_contents


def walk_directory_for_files(dataset_path: str) -> List[str]:
    """Walk through directory and subdirectories and return a list of all files"""
    file_paths = []
    for root, _, files in os.walk(dataset_path):
        for file in files:
            full_path = os.path.join(root, file)
            if os.path.isfile(full_path):
                file_paths.append(full_path)
    return file_paths


def _read_json(file_path) -> list:
    """Reads a JSON file and returns a list of JSON objects."""
    with open(file_path, "r", encoding="utf-8") as file:
        loaded_json = json.load(file)
        if isinstance(loaded_json, list):
            return loaded_json
        else:
            return [loaded_json]


def _read_jsonl(file_path) -> list:
    """Reads a JSONL file and returns a list of JSON objects."""
    data = []
    with open(file_path, "r", encoding="utf-8") as file:
        for line in file:
            json_object = json.loads(line.strip())
            data.append(json_object)
    return data
