# Universal NCCL configuration (helm NCCL test + multicloud baseline)
export NCCL_DEBUG=INFO
export NCCL_DEBUG_SUBSYS=ALL
export NCCL_DEBUG_FILE=/tmp/nccl_debug.log
export NCCL_TREE_THRESHOLD=0
export NCCL_RING_THRESHOLD=8
export NCCL_BUFFSIZE=8388608
export NCCL_NTHREADS=32
export NCCL_MAX_NCHANNELS=32

echo "=== Universal NCCL Configuration Loaded ==="
echo "NCCL_DEBUG: $NCCL_DEBUG"
echo "CUDA_VISIBLE_DEVICES: $CUDA_VISIBLE_DEVICES"
echo "NCCL_BUFFSIZE: $NCCL_BUFFSIZE"
