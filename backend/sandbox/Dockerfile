# AgenticAPI 维护 Agent 容器沙箱镜像
# 由 sandbox_service 在首次使用时懒构建（指纹 = sha256(Dockerfile 内容 + BASE_IMAGE)），
# 修改本文件后指纹变化，下次 ensure_ready() 自动重建。
#
# 基础镜像可经 .env SANDBOX_BASE_IMAGE 覆盖（Docker Hub 拉取慢时换国内镜像源，
# 如 docker.m.daocloud.io/library/python:3.12-slim）。
ARG BASE_IMAGE=python:3.12-slim
FROM ${BASE_IMAGE}

# curl/jq：API 拨测与 JSON 处理；httpx：异步 HTTP 脚本；ca-certificates：HTTPS
RUN apt-get update && apt-get install -y --no-install-recommends curl jq ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir httpx

# 非 root 运行（配合宿主侧 -u 1000:1000 / --cap-drop ALL / --read-only）
RUN useradd -m -u 1000 sandbox
USER 1000
WORKDIR /workspace

# 常驻睡眠等待 docker exec 注入命令（容器由 sandbox_service 懒启动/空闲自停）
CMD ["sleep", "infinity"]
