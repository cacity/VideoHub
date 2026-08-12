# VideoHub 付费支持申请 / Paid Support Request

请复制下面的字段到邮件正文，并附上无密钥预检报告。不要发送密码、Cookie、Token、API Key、私人素材或完整客户数据。

联系：**stark fng** · [gf7823332@gmail.com](mailto:gf7823332@gmail.com?subject=VideoHub%20paid%20support%20request)

## 申请模板

```text
服务档位：QuickStart USD 299 / Creator USD 999 / Team USD 2,999 / 不确定
操作系统与版本：
个人或团队：
希望跑通的一个明确流程：
输入类型和大致数量/时长：
目标输出（语言、字幕、配音、画幅、平台）：
授权样例：可提供 / 尚未准备
目标开始日期与时区：
预检 JSON/Markdown：已附 / 尚未运行
第三方付费服务：可自行配置 / 希望避免 / 不确定
补充说明：
```

## 生成无密钥预检报告

在 VideoHub 仓库根目录运行：

```powershell
python src/support_preflight.py
```

命令会生成：

- `videohub_support_report.json`
- `videohub_support_report.md`

报告不联网、不扫描媒体，只记录系统版本、Python/FFmpeg、关键包、磁盘、目录可写性，以及可选 API 凭据是否配置。报告不会包含凭据值，相关文件默认不进入 Git。发送前仍建议自行打开检查。

## 如何选择档位

- 只需在一台 Windows 电脑安装并跑通一个样例：QuickStart USD 299。
- 需要统一三个系列样例的字幕、音色、画幅和封面：Creator USD 999。
- 需要私有部署、定制团队流程、验收测试和培训：Team USD 2,999。

正式排期前会书面冻结范围、材料、验收标准与付款节点。预检通过不代表自动接受项目；素材权利、平台限制和第三方费用仍需单独确认。

---

## English template

Copy these fields into your email and attach the secret-safe preflight report. Do not send passwords, cookies, tokens, API keys, private media, or complete customer datasets.

```text
Service tier: QuickStart USD 299 / Creator USD 999 / Team USD 2,999 / unsure
OS and version:
Individual or team:
One workflow to make repeatable:
Input type and approximate count/duration:
Target output (language, subtitles, voice, aspect ratio, platform):
Authorized sample: ready / not ready
Target start date and timezone:
Preflight JSON/Markdown: attached / not run
Third-party paid services: self-managed / prefer none / unsure
Additional notes:
```

Run `python src/support_preflight.py` from the repository root. It makes no network calls, scans no media, and reports only versions, executable/package status, storage, writable directories, and whether optional credentials are configured. Secret values are never included.

