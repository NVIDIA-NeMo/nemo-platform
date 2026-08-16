# Matches the tag CI pre-pulls in the integration job, so building this task image reuses that
# layer
FROM alpine:3.23

# bash is required for Harbor's docker environment
RUN apk add --no-cache bash

WORKDIR /app
