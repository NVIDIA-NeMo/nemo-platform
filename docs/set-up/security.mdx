<a id="nemo-ms-admin-setup-security"></a>
# Security for {{platform_name}}

This page provides security guidelines and best practices for deploying and managing {{platform_name}} in production environments.

## Security Considerations

- The {{platform_name}} does not impose rate limits. You must implement a rate-limiting strategy to restrict access to your application.
- The {{platform_name}} does not have an internal notion of a user. To restrict authorization to specific endpoints or users, implement an external mechanism such as an Envoy proxy.
- The {{nds_short_name}} microservice does not provide object-class-specific access controls. All items reside within a single access control boundary.
- The {{platform_name}}, by design, can access all content in the {{nds_short_name}} microservice, including LoRA adapters, training data, evaluation data, and evaluation results. 
 This access is required for model evaluation. 
 Carefully weigh the risk of data exposure from serving customized models directly to production against the overhead of a separate deployment.
- The {{platform_name}} is not intended to be internet-facing. Deploy them as the logic (middle) tier in a three-tier architecture.
- You are responsible for securing access to any application using the microservices. This includes:
 - Implementing an authentication layer between users and your application
 - Applying required authorization controls
 - Securing communication between services in your application

!!! note
    Refer to the [NVIDIA Product Security](https://www.nvidia.com/en-us/security/psirt-policies/) page for information about subscribing to bulletins and updates, managing vulnerabilities, and reporting vulnerabilities.

## Default Network Ports

The following table lists the default network ports for each microservice or default database. You can override these port numbers during deployment.

| Network Port | Microservice |
| --- | --- |
| 443/TCP | NeMo Admission Service API |
| 3000/TCP | {{nds_short_name}} API |
| 7331/TCP | {{nem_short_name}} API |
| 7331/TCP | {{ngm_short_name}} API |
| 8000/TCP | {{nim_short_name}} API |
| 8000/TCP | NeMo Retriever Text Embedding API |
| 8000/TCP | NeMo Retriever Text Reranking API |
| 8000/TCP | {{ncm_short_name}} API |
| 8000/TCP | {{nes_short_name}} API |
| 8443/TCP | {{nop_short_name}} metrics |
| 8080/TCP | Volcano Scheduler metrics |
| 9009/TCP | {{ncm_short_name}} callback |

By default, the {{helm_chart_short_name}} configures databases with the following network ports. 
Alternatively, you can configure each microservice to use an external database during installation.

| Network Port | Database |
| --- | --- |
| 5432/TCP | {{ncm_short_name}} Database |
| 5432/TCP | {{nds_short_name}} Database <!-- nemo-postgresql --> |
| 5432/TCP | {{nem_short_name}} Database |
| 5432/TCP | {{nes_short_name}} Database |
| 9091/TCP | Milvus metrics |
| 19530/TCP | Milvus API |

By default, the {{helm_chart_short_name}} installs an open telemetry collector, which uses the following network ports:

- 4317/TCP
- 4318/TCP
- 6831/UDP
- 9411/TCP
- 14250/TCP
- 14268/TCP

Refer to the [OpenTelemetry Documentation](https://opentelemetry.io/docs/) for more information.
