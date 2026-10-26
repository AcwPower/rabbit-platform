# 小白兔组队平台实施方案

依据 PRD V2，部署目标为腾讯云 Ubuntu，独立于其他网站，不使用 Docker。

## 架构

Vue 3 / Vite / Tailwind CSS 前端；FastAPI / SQLAlchemy / Alembic 后端；MySQL 8，utf8mb4；所有日期保存 UTC，界面使用 Asia/Shanghai。独立 Linux 服务账号 rabbit、目录 /opt/rabbit-platform、MySQL 用户 rabbit_app 和数据库 rabbit_platform、Python venv、systemd 服务 rabbit-api / rabbit-ocr、Nginx 站点 rabbit-platform。OCR 使用独立受资源限制的 RapidOCR / ONNX CPU 中英文进程，普通识别图片只保存在临时目录并立即删除；注册合格截图单独加密保存在数据库，详见 REGISTRATION-SCREENSHOTS.md。

## 数据与鉴权

账号使用 PBKDF2 密码哈希、HttpOnly 会话 Cookie 和 CSRF；匿名管理凭证由浏览器产生 256 位随机数，放 URL fragment，在服务端仅存 SHA256。微信号和二维码加密保存，授权后读取，到期清理。发布者、多角色、双向卡片、申请、撮合、评价、举报、审计独立建模。邮箱恢复仅在 SMTP 配置完整时开放，绑定邮箱先验证。

## 状态与事务

接受申请创建 contacted 撮合但不占坑；boarded 在事务中锁定队伍卡和撮合记录，再检查容量；完成需双方确认，完成或取消释放占用。过期由定时任务处理。所有业务写操作带幂等键，匿名新建时不在幂等缓存中保存明文凭证。公共列表不提供联系方式。

## 测试

单元与 API 测试覆盖登录/CSRF、匿名凭证、双方权限、状态转换、重复申请、过期、编辑不置顶、上传检查、举报审核和评价。另在独立 MySQL 测试库对最后一个坑位执行真正的并发请求。浏览器实测移动布局、筛选抽屉、发布表单、OCR 图片粘贴、人工确认和普通文本粘贴。注册、申请和管理凭证权限由 MySQL API 测试覆盖。OCR 使用生成的英文角色截图测试；已增加真实拍屏的双区域识别，模糊中文名字仍需人工核对。

## 部署与回滚

安装前检查运行服务与端口；备份现有配置和数据库；新版本放 releases/<timestamp>，迁移预检后运行 Alembic，current 软链接切换，执行健康检查。回滚先切回上版代码；涉及不兼容数据库迁移时停服务并从上线前 SQL 备份恢复。恢复脚本需显式确认参数。HTTPS 和公网访问完成后才标记生产上线通过。
