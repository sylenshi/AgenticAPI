# AgenticAPI 维护 Agent 容器沙箱镜像
# 由 sandbox_service 在首次使用时懒构建（指纹 = sha256(Dockerfile 内容 + BASE_IMAGE + PIP_INDEX_URL + APT_MIRROR)），
# 修改本文件或任一来源变化时指纹变化，下次 ensure_ready() 自动重建。
#
# 基础镜像可经 .env SANDBOX_BASE_IMAGE 覆盖（Docker Hub 拉取慢时换国内镜像源，
# 如 docker.m.daocloud.io/library/python:3.12-slim）。
ARG BASE_IMAGE=python:3.12-slim
FROM ${BASE_IMAGE}

# pip 源可经 .env SANDBOX_PIP_INDEX_URL 覆盖（pypi.org 不可达的内网环境换国内镜像，
# 如 https://mirrors.tencentyun.com/pypi/simple）。
ARG PIP_INDEX_URL=https://pypi.org/simple

# Debian apt 源主机可经 .env SANDBOX_APT_MIRROR 覆盖（deb.debian.org 海外下载慢时
# 换国内源，如 mirrors.cloud.tencent.com；同时覆盖 sources.list 与 debian.sources）。
ARG APT_MIRROR=deb.debian.org

# curl/jq：API 拨测与 JSON 处理；httpx：异步 HTTP 脚本；ca-certificates：HTTPS
RUN set -eux; \
    for f in /etc/apt/sources.list /etc/apt/sources.list.d/debian.sources; do \
        [ -f "$f" ] && sed -i "s|deb.debian.org|${APT_MIRROR}|g" "$f" || true; \
    done; \
    apt-get update && apt-get install -y --no-install-recommends curl jq ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir --index-url ${PIP_INDEX_URL} httpx

# 非 root 运行（配合宿主侧 -u 1000:1000 / --cap-drop ALL / --read-only）
RUN useradd -m -u 1000 sandbox
USER 1000
WORKDIR /workspace

# 常驻睡眠等待 docker exec 注入命令（容器由 sandbox_service 懒启动/空闲自停）
CMD ["sleep", "infinity"]
