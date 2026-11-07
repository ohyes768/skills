# Hermes AI 任务触发镜像（task-web docker 引擎按次拉起）
# 源码：skills 仓库 personal-tools/hermes-trigger/；由 deploy-nas.sh task-web 构建
FROM python:3.12-slim
RUN pip install --no-cache-dir requests
WORKDIR /app
COPY hermes_trigger.py .
CMD ["python", "hermes_trigger.py"]
