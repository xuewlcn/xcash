# 多阶段构建：modernc.org/sqlite 是纯 Go 实现，可 CGO_ENABLED=0 静态编译，
# 运行镜像用 distroless/static:nonroot，无 shell、无包管理器，以非 root 运行，攻击面最小。
FROM golang:1.26 AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/signer ./cmd/signer
# 预置 /data 目录，供下一阶段以 nonroot 属主拷入
RUN mkdir -p /data

FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=build /out/signer /signer
# 把 /data 以 nonroot(65532) 属主拷入：首次挂载的空命名卷会继承该属主，
# 使非 root 进程能在卷上创建并写入 SQLite 文件。
COPY --from=build --chown=65532:65532 /data /data
VOLUME ["/data"]
EXPOSE 8000
ENTRYPOINT ["/signer"]
