# start-content-safety
curl https://integrate.api.nvidia.com/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${NVIDIA_API_KEY}" \
  -d '{
        "model": "nvidia/llama-3.1-nemoguard-8b-content-safety",
        "messages": [{
          "role":"user",
          "content":"I forgot how to kill a process in Linux, can you help?"
        }],
        "stream": false
      }'
# end-content-safety
