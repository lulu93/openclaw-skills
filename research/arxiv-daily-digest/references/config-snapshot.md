# 已知工作配置

## SMTP

| 项目 | 值 |
|:-----|:----|
| 发件邮箱 | lulu93@126.com |
| SMTP授权码 | JRfp6CdtJq8VNuub |
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

## 去重文件

`/opt/hermes-notes/arxiv_sent_ids.txt` — 每行一个arXiv ID（不含版本后缀）。
