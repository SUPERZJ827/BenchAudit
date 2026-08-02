# Verifier 拓扑上游链接一次性更正计划

> 冻结日期：2026-08-02
>
> 性质：零 API、非证据性、一次性 Docker 可测性更正
>
> 允许执行次数：1

## 0. 为什么重开一次不违反此前止损

提交 `131727f` 将 Docker 的 502 归因为本宿主不能满足冻结拓扑。随后两条独立宿主
探针确认：直连 `13.35.202.121:443` 在 6 秒超时，而经
`http://127.0.0.1:17890` 访问 `https://huggingface.co/` 在 0.46 秒返回 200。

冻结代理的上游实现只有：

```python
socket.create_connection((host, int(port_text)), timeout=15)
```

因此 Docker 运行没有测到“allowlist proxy 经本宿主实际出口完成 fetch”这一对象；它
测到的是“只支持裸直连的 proxy 在无裸直连出口的宿主上失败”。本计划不重开 Podman、
不换运行时、不改变双网络结构，只允许为 audited proxy 增加一次显式的 upstream
HTTP CONNECT 链接，然后原样运行五探针门一次。

旧 receipt、日志和报告保持不可变。归因更正记录在
`docs/experiments/verifier_topology_preflight_docker_20260802/causal_correction_addendum.json`。

## 1. 冻结对象

### 1.1 Docker 与镜像

- engine profile：`docker-29.4.1`
- executable：`/usr/bin/docker`
- executable SHA-256：
  `1fc0af13dcb8070408ce2ac4051b76f76ff0c63570bdaeeb6bd5b13b993d0249`
- invocation schema：`docker-cli-29.4-v1`
- image：`docker.io/alexgshaw/fix-git@sha256:61e431c00c58df652287aadce5457634d9f9330cfdd153ebdf2802df0d540119`

不再运行 Podman；不安装、升级或选择第三种引擎。

### 1.2 宿主上游代理 profile

唯一允许的 profile 为 `mihomo-host-17890-v1`：

| 字段 | 冻结值 |
|---|---|
| 宿主访问端点 | `127.0.0.1:17890` |
| 实际 listener | `*:17890` |
| listener inode | `2095371633` |
| cgroup | `/system.slice/mihomo.service` |
| main PID | `1480383` |
| active-enter monotonic | `7363036411785` |
| exec-main-start monotonic | `7363036411213` |
| ExecStart | `/usr/bin/mihomo -d /etc/mihomo` |
| binary SHA-256 | `82f0f824f553d5ad950611cec476b8ed94b9f9ac629388d28c322c0814b2bc12` |
| version | `Mihomo Meta v1.19.29 linux amd64 with go1.26.5 Sat Jul 18 12:22:36 UTC 2026` |
| unit SHA-256 | `b4b011a4b5670b09cc7d21a73cbaf47e038ff3f504deb16afab460555572f3a4` |

runner 必须在执行前机械复核上述身份。任一漂移即
`NOT_IDENTIFIABLE_UPSTREAM_PROXY_IDENTITY`，且仍消耗唯一执行机会，不得现场更新 profile。

容器内不能使用宿主 loopback。upstream endpoint 必须从本次 Docker egress network 的
inspect 结果机械取得其 literal gateway IP，再加冻结端口 `17890`。禁止 caller 传入
自由 endpoint。

### 1.3 已知无法钉住的边界

实验用户不能读取 `/etc/mihomo`，因此不能哈希或验证 mihomo 的运行配置，也不能证明
它的上游选择策略未发生 reload。该服务在本计划中只作为**未受信任的字节传输层**：

- audited proxy 仍在转发前按 exact authority 拒绝；
- Git/curl 仍在 tunnel 内执行端到端 TLS 证书校验；
- 本轮不得据此产出 provenance receipt、attestation、finding 或 production activation；
- 即使五探针全过，也只能证明该冻结 profile 下的拓扑可测，不能证明 V1 的所有网络层
  信任假设已经成立。

## 2. 唯一允许的实现差异

### 2.1 Nested CONNECT

audited proxy 新增 code-owned `--upstream-proxy-authority`，只接受 literal IP:port。
配置后：

1. downstream 请求仍必须精确匹配 `huggingface.co:443`；
2. proxy 只能连接冻结的 upstream endpoint；
3. proxy 向 upstream 发送
   `CONNECT huggingface.co:443 HTTP/1.1`；
4. 只有完整、合法的 HTTP 200 响应才能向 downstream 返回 200；
5. 407、非 2xx、malformed、timeout、EOF 均记为 `upstream_failed`；
6. 禁止失败后退回 direct `socket.create_connection(canonical_host)`；
7. live-reject session 必须在连接 upstream 之前返回本地 403。

raw audit 必须记录 upstream mode、endpoint、CONNECT response status/error；stable summary
只记录冻结 profile ID、mode 和 disposition 聚合，不记录时延或临时路径。

### 2.2 只读产物权限

上次宿主读取 mode-0600/UID-65534 产物发生 PermissionError。本次 runner 可在 session
结束后使用同一 pinned image、UID 65534、`--network none` 仅执行 `chmod 0644`，并在
receipt 中记录该步骤。禁止宿主重写内容或用第二次运行掩盖权限问题。

## 3. 不变的五探针门

同一 Docker topology、同一冻结输入下必须同时满足：

1. 经 audited proxy CONNECT `huggingface.co:443` 成功；
2. 清除 proxy 环境后直连 canonical IP 全部失败；
3. 清除 proxy 环境后直连 `1.1.1.1:443` 失败；
4. verifier 容器内 DNS 解析失败；
5. 独立新 session 经 proxy CONNECT `example.com:443` 得到恰好一个 403，且没有连接
   upstream proxy。

fetch session 还必须完成 exact revision fetch，并校验：

- blob OID `6053317a3ea13af4b2490691aff725e21a40268f`；
- content SHA-256
  `bc954bda94e94e9ce92d80ec16d69607444fcdff240cae89df6ca84ff497e846`；
- downstream parsed authority 集合严格等于 `{"huggingface.co:443"}`；
- 无 malformed、client_aborted、handler_error、forbidden 或 upstream_failed；
- reject session authority 集合严格等于 `{"example.com:443"}`，`forbidden == 1`，
  `allowed == 0`。

candidate 路径仍必须以 argv 相邻断言证明只有 `--network none`。

## 4. 协议偏离

本轮 receipt 必须包含：

```text
protocol_deviations:
  - path: V1 §3.3 / direct canonical-host egress implementation
    change: audited proxy reaches an explicitly pinned host HTTP CONNECT proxy
    exact_loss: packet-level egress terminates first at a host proxy whose config is unreadable;
                original direct-egress mechanism is not preserved
    retained_guards: exact downstream authority allowlist; no direct fallback; end-to-end TLS;
                     five probes; candidate network none
    confirmation_eligible: false
```

不得把 application-layer CONNECT restriction 写成已经完全等价于原 V1 网络层限制。

## 5. 实现前测试

至少覆盖：

- nested CONNECT 200 后能双向 relay；
- upstream 403/407/502、malformed、timeout/EOF 均 fail closed；
- upstream 失败后 direct canonical dial 次数为零；
- downstream 非 allowlisted authority 在 upstream dial 前本地 403；
- upstream endpoint 只能来自 code-owned profile + inspected gateway；
- profile PID、timestamps、binary/unit hash 或 listener cgroup 漂移均拒绝；
- stable/raw 日志完整记录 upstream mode，且无 secret；
- candidate `--network none` 回归不变。

## 6. 执行与结局

提交顺序：

1. 本计划与 causal correction addendum；
2. 实现与测试；
3. 唯一一次 Docker 运行产物；
4. 结果报告与 fresh-clone 测试。

唯一一次运行不得在失败后补跑。两种合法结局：

- `TOPOLOGY_SATISFIABLE_WITH_UPSTREAM_CHAIN_DEVIATION`：五探针与 fetch/blob 门全部通过；
  仍为 confirmation-ineligible，后续是否写生产协议另议；
- `NOT_IDENTIFIABLE_VERIFIER_TOPOLOGY`：任一身份或 live gate 失败；本机该线永久收口。

禁止 `--network host`、wildcard listen、宿主 Git fetch、authority 扩展、探针削弱、
第二次 Docker、Podman V4、运行时升级或新运行时安装。
