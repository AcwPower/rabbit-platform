# 小白兔组队平台

已部署入口：**https://mushroom-king-timer.online/party/**

面向冒险岛怀旧服的小队招募与老板求车平台。移动端优先，免注册浏览和老板申请；打手注册后发布队伍、管理申请及微信资料；实际微信/二维码联系渠道加密保存，同意后授权展示。支持截图粘贴识别、上车确认、双向完成、评价审核、举报与管理员处置。

## 部署位置

| 组件 | 位置 |
|---|---|
| 公网 HTTPS、原计时器 | `43.161.217.238`，原域名根路径保持原服务 |
| `/party/` 前端和 API | `43.161.232.10`，`/opt/rabbit-platform/current` |
| MySQL | 新机器本地 `rabbit_platform`，独立账号 |
| OCR | 独立 `rabbitocr` 用户及 systemd 服务，仅监听回环地址 |
| 新网关片段 | `.238` 的 `/etc/nginx/snippets/rabbit-platform.conf` |

没有合并 `AcwPower/mushroom` 源码或数据库。两端均使用 HTTPS；实测两机私网地址不互通，因此网关通过公网 `.10:443` 转发，严格校验固定的后端证书。后端 Nginx 仅允许网关地址和本机访问；API、OCR、MySQL 不直接对公网监听。

## 技术与源码

- `frontend/`：Vue 3、Vite、Tailwind CSS、Lucide，`pnpm-lock.yaml` 锁定依赖。
- `backend/`：FastAPI、SQLAlchemy、Alembic、MySQL，`requirements.txt` 来自实际部署环境。
- `deploy/`：发布、备份、恢复演练、代码回滚、systemd、Nginx 配置。
- [找队友、祭司求职与热门地图](docs/PARTNERS-AND-MAPS.md)
- [注册截图审核与存储](docs/REGISTRATION-SCREENSHOTS.md)、[双框 OCR 更新说明](docs/OCR-DUAL-REGIONS.md)、[运维与管理员说明](docs/OPERATIONS.md)、[实际验收报告](docs/ACCEPTANCE.md)、[OpenAPI](docs/openapi.json)。

## 本地开发

Node.js 22+、pnpm 11.25、Python 3.12+，生产验证环境为 Ubuntu 26.04 / Python 3.14 / MySQL 8.4。准备一个独立 MySQL 开发库；复制 `backend/.env.example` 为 `backend/.env` 并生成自己的随机密钥。

```sh
cd backend
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --host 127.0.0.1 --port 8101
```

另开终端运行前端：

```sh
cd frontend
pnpm install --frozen-lockfile
pnpm dev --host 127.0.0.1
```

访问 `http://127.0.0.1:5173/party/`。开发配置 `PUBLIC_ORIGIN=http://127.0.0.1:5173`、`COOKIE_SECURE=false`；生产必须使用 HTTPS 和 Secure Cookie。OCR 使用 `OCR_SECRET` 启动独立 `app.ocr_worker:app`，首次部署执行 `python -m app.ocr_engine --prepare` 预检本地模型。

## 测试

`TEST_ENV_FILE` 指向独立测试配置，数据库名称必须以 `_test` 结尾。

```sh
cd backend
TEST_ENV_FILE=/absolute/path/test.env .venv/bin/python -m pytest -q
```

测试会重建测试库表，**不能使用生产库**。最后坑位并发用例依赖真实 MySQL，不能以 SQLite 代替。邮箱恢复提供配置开关和实际 SMTP 发送逻辑，但当前未配置发信邮箱，不对用户宣称可用。OCR 已用合成文字截图验证，已验证一张真实游戏拍屏图的等级、职业和地图；模糊角色名仍需人工核对。

## 发布

```sh
cd frontend
pnpm build
cd ..
python3 deploy/package.py /tmp/rabbit-release.tgz
scp /tmp/rabbit-release.tgz ubuntu@43.161.232.10:/home/ubuntu/
```

将 `deploy/install-release.sh` 复制至新机器，然后执行 `sudo bash install-release.sh /home/ubuntu/rabbit-release.tgz <唯一版本号>`。发布脚本备份现有部署、安装独立版本 venv、迁移数据库、更新服务、健康检查。首次部署的系统依赖、网关接入和回滚操作详见运维说明。任何凭证均不应加入源码包。

第一版导航、提醒、微信频率限制和管理员角色修改规则见 [docs/NOTIFICATIONS-PROFILES-V1.md](docs/NOTIFICATIONS-PROFILES-V1.md)。

## 广场卡片进度与排序

挂绳队伍卡片默认仅展示当前已上车老板的匿名编号与已挂百分比；展开后显示进度条、已挂时长、实际上车和预计结束时间，每 30 秒刷新。百分比以实际上车至预计结束的时段计算，最高 100%；到时仍需打手手动结束挂机，不自动释放名额。没有已上车老板时显示「暂无老板上车」。公开接口仅返回编号与时间，不包含老板姓名、联系方式或申请记录标识。

队伍列表默认「优先可上车」：有空位的队伍优先，同档按发布时间从新到旧；满员队伍按下一位老板未来的预计结束时间从近到远；只剩已到时或时间未知的满员队伍最后展示。预计结束仅供等待参考。排序在数据库分页之前完成，支持 `sort=availability`（默认）与 `sort=latest`，页面也可切换「最新发布」。筛选条件仍优先限制候选队伍。
