# 管理端 App(后端 + 演示 PWA)

实验室巡检机器人的管理端:后端把机器人产出的**安全告警 / 工位记录 / 课后验收 / 巡检报告**(+证据图)
落库并以 REST + SSE 暴露;演示用 PWA(手机网页)展示。**接口契约见 [`API_SPEC.md`](API_SPEC.md)**——正式 App 照它开发。

## 结构
```
app/backend/   FastAPI 后端(纯逻辑 store/ingest/query/assets/push + 薄 server)
app/web/       演示 PWA(原生 JS,无构建步骤)
app/data/      seed/(种子数据+示例图) assets/(物资CSV) runtime/(运行期DB+上传图,git忽略)
rdk_x5/.../inspection_manager/uplink_node.py  机器人侧上行节点(把ROS话题POST到本后端)
```

## 本地起(Mac,无需机器人)
```bash
# 1) 装依赖(建议 venv)
python3 -m venv ~/.venvs/inspection && ~/.venvs/inspection/bin/pip install -r app/backend/requirements.txt
# 2) 灌种子数据
python3 -m app.backend.seed                       # 用 venv 的 python 亦可
# 3) 起服务(绑 0.0.0.0 供手机访问)
~/.venvs/inspection/bin/uvicorn app.backend.server:app --host 0.0.0.0 --port 8000
# 4) 浏览器/手机打开
#    桌面: http://localhost:8000   手机(同热点): http://<Mac局域网IP>:8000
# 5) (可选)模拟实时告警,演示 SSE 推送
python3 -m app.backend.sim_feed
```
> 写接口鉴权:设环境变量 `APP_INGEST_TOKEN=xxx` 后,POST/PUT 需 `Authorization: Bearer xxx`;不设则写接口开放(开发用)。

## 测试
```bash
python3 -m unittest discover -s tests          # 含 test_app_* 与 test_uplink
```

## 演示功能(PWA 四 tab)
- **告警**:实时推送(SSE)+ 证据图 + 处理按钮
- **工位**:工位记录 + 课后验收(照片/结论/问题清单)
- **报告**:L3 巡检报告(Markdown 渲染)
- **物资**:设备/耗材位置查询

## 上板联调(最后一步)
把 `inspection_manager` 重建部署到 RDK,起 `uplink_node`(`backend_url` 指 Mac IP),
跑巡检栈 → 真实事件/记录/报告/证据图 实时上手机。详见 `config/uplink.yaml`。
