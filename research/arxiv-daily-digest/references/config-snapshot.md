# 已知工作配置

## SMTP

| 项目 | 值 |
|:-----|:----|
| 发件邮箱 | lulu93@126.com |
| SMTP授权码 | 见 `~/.hermes/.env` 的 `SMTP_PASSWORD`（凭据不入库） |
| 收件邮箱 | sunlu28@huawei.com |
| 服务器 | smtp.126.com:465 (SSL) |
| 代码模板 | `MIMEMultipart('alternative')`，只发文本+HTML，不加附件 |

## Clash Proxy

| 项目 | 值 |
|:-----|:----|
| 二进制 | `/usr/local/bin/mihomo` |
| 配置目录 | `/root/.config/clash/` |
| 启动命令 | `mihomo -d /root/.config/clash/ &` |
| HTTP代理端口 | 127.0.0.1:7890 |
| 控制API | http://127.0.0.1:9090 |
| 重载配置 | `curl -X PUT http://127.0.0.1:9090/configs -d '{"path":"/root/.config/clash/config.yaml"}'` |

### 必要Proxy规则

```yaml
- DOMAIN-SUFFIX,arxiv.org,Proxy
- DOMAIN-SUFFIX,arxivstatic.com,Proxy
- DOMAIN-SUFFIX,export.arxiv.org,Proxy
```

加在 `- DOMAIN-SUFFIX,pypi.org,Proxy` 之后。

### 节点故障处理

AnyTLS/Trojan节点可能延迟为0不可用。切换到Auto（URLTest模式）自动选Hysteria2节点：

```bash
curl -s -X PUT http://127.0.0.1:9090/proxies/Proxy -d '{"name":"Auto"}' -H "Content-Type: application/json"
sleep 10  # 等待URLTest收敛
```

### ⭐ arxiv.org无需代理

**arxiv.org可直连** — RSS下载、PDF下载、abstract页面提取都不需要走Clash代理。仅NotebookLM/Google需要代理。

## 去重文件

`/opt/hermes-notes/arxiv_sent_ids.txt` — 每行一个arXiv ID（不含版本后缀）。
