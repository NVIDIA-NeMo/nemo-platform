// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// API Reference page: chip-based tag filtering for Swagger UI iframe
(function() {
  function initApiFilter() {
    var chips = document.querySelectorAll('.api-chip');
    var chipContainer = document.querySelector('.api-filter-chips');
    var iframe = document.querySelector('iframe.swagger-ui-iframe');
    if (!chipContainer || !iframe) return;
    var hiddenTags = {};
    if (chipContainer.dataset.hiddenTags) {
      chipContainer.dataset.hiddenTags.split(',').forEach(function(tag) {
        tag = tag.trim();
        if (tag) hiddenTags[tag] = true;
      });
    }
    var hiddenTagIds = {};
    Object.keys(hiddenTags).forEach(function(tag) {
      hiddenTagIds['operations-tag-' + tag.replace(/ /g, '_')] = true;
    });
    var retryTimer = null;
    var swaggerObserver = null;

    function tagSlug(tag) {
      return tag.toLowerCase().trim().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
    }

    function chipHash(chip) {
      var id = chip.getAttribute('id');
      if (id) return '#' + id;

      var tag = chip.getAttribute('data-tag') || '';
      return tag ? '#tag-' + tagSlug(tag) : '#tag-all';
    }

    function tagFromHash() {
      var hash = window.location.hash;
      if (!hash) return '';

      var selectedTag = '';
      var normalizedHash = decodeURIComponent(hash).toLowerCase();
      chips.forEach(function(chip) {
        var tag = chip.getAttribute('data-tag') || '';
        if (chipHash(chip).toLowerCase() === normalizedHash) {
          selectedTag = tag;
        }
      });

      return hiddenTags[selectedTag] ? '' : selectedTag;
    }

    function getDoc() {
      try { return iframe.contentDocument || iframe.contentWindow.document; }
      catch(e) { return null; }
    }

    function applyFilter(tag) {
      var doc = getDoc();
      if (!doc || !doc.querySelectorAll('.opblock-tag-section').length) return false;
      if (hiddenTags[tag]) tag = '';
      var tagId = tag ? 'operations-tag-' + tag.replace(/ /g, '_') : '';
      doc.querySelectorAll('.opblock-tag-section').forEach(function(s) {
        var heading = s.querySelector('.opblock-tag');
        var id = heading ? heading.getAttribute('id') : '';
        s.style.display = (!hiddenTagIds[id] && (!tag || id === tagId)) ? '' : 'none';
      });
      iframe.style.visibility = '';
      return true;
    }

    function setActiveChip(tag) {
      chips.forEach(function(chip) {
        var isActive = (chip.getAttribute('data-tag') || '') === tag;
        chip.classList.toggle('active', isActive);
      });
    }

    function updateUrl(chip) {
      var nextUrl = window.location.pathname + window.location.search + chipHash(chip);
      if (window.location.href !== window.location.origin + nextUrl) {
        window.history.pushState(null, '', nextUrl);
      }
    }

    function selectTag(tag, chip, shouldUpdateUrl) {
      if (hiddenTags[tag]) tag = '';
      setActiveChip(tag);
      if (!applyFilter(tag)) scheduleTryInit(50);
      if (shouldUpdateUrl && chip) updateUrl(chip);
    }

    function syncFromHash() {
      selectTag(tagFromHash(), null, false);
    }

    function bindChips() {
      chips.forEach(function(chip) {
        if (hiddenTags[chip.getAttribute('data-tag')]) {
          chip.style.display = 'none';
          return;
        }
        if (chip.dataset.apiFilterBound) return;
        chip.dataset.apiFilterBound = 'true';
        chip.addEventListener('click', function() {
          selectTag(chip.getAttribute('data-tag') || '', chip, true);
        });
      });
    }

    function scheduleTryInit(delayMs) {
      if (retryTimer) return;
      retryTimer = setTimeout(function() {
        retryTimer = null;
        tryInit();
      }, delayMs);
    }

    function disconnectObserver() {
      if (!swaggerObserver) return;
      swaggerObserver.disconnect();
      swaggerObserver = null;
    }

    function watchSwaggerDoc(doc) {
      if (swaggerObserver || !doc || !doc.body || typeof MutationObserver === 'undefined') return;
      swaggerObserver = new MutationObserver(function() {
        if (doc.querySelectorAll('.opblock-tag-section').length) {
          disconnectObserver();
          tryInit();
        }
      });
      swaggerObserver.observe(doc.body, { childList: true, subtree: true });
    }

    function tryInit() {
      var doc = getDoc();
      if (!doc || !doc.body) {
        scheduleTryInit(50);
        return;
      }
      if (!doc.querySelectorAll('.opblock-tag-section').length) {
        watchSwaggerDoc(doc);
        scheduleTryInit(250);
        return;
      }

      disconnectObserver();
      var filterBar = doc.querySelector('.filter-container');
      if (filterBar) filterBar.style.display = 'none';

      bindChips();
      syncFromHash();
    }

    window.__apiFilterSyncFromHash = syncFromHash;
    if (!window.__apiFilterHashListenerBound) {
      window.__apiFilterHashListenerBound = true;
      window.addEventListener('hashchange', function() {
        if (window.__apiFilterSyncFromHash) window.__apiFilterSyncFromHash();
      });
      window.addEventListener('popstate', function() {
        if (window.__apiFilterSyncFromHash) window.__apiFilterSyncFromHash();
      });
    }

    if (tagFromHash()) iframe.style.visibility = 'hidden';
    bindChips();
    syncFromHash();
    iframe.addEventListener('load', function() {
      disconnectObserver();
      scheduleTryInit(0);
    });
    scheduleTryInit(0);
  }

  // MkDocs Material instant navigation re-renders pages without full reloads
  if (typeof document$ !== 'undefined') {
    document$.subscribe(function() { setTimeout(initApiFilter, 0); });
  } else {
    document.addEventListener('DOMContentLoaded', function() {
      setTimeout(initApiFilter, 0);
    });
  }
})();
