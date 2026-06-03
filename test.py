import cupy as cp

x = cp.random.random((10000, 10000))
y = cp.sum(x)

cp.cuda.Stream.null.synchronize()

print(y)