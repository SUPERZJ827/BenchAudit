# BenchAudit Verifier 拓扑双引擎最终裁决

> 日期：2026-08-02
>
> 分支：`research/verifier-topology-preflight-20260802`
>
> 最终裁决：`NOT_IDENTIFIABLE_VERIFIER_TOPOLOGY`
>
> 状态：本宿主上的该实验线已收口；不再迭代 Podman，不再重跑 Docker。

## 1. 结论

同一道已冻结的 verifier 拓扑门在本机全部两个 code-owned 容器引擎上均未通过：

| 引擎 | 绑定 | 结局 | 首个实质失败 |
|---|---|---|---|
| Podman | 3.4.4 / `/usr/bin/podman` / executable SHA-256 `02a39025…` | `NOT_IDENTIFIABLE` | 冻结的双网络静态-IP拓扑无法在旧 CNI 栈上实例化 |
| Docker | client/server 29.4.1 / `/usr/bin/docker` / executable SHA-256 `1fc0af13…` | `NOT_IDENTIFIABLE` | 隔离负控通过，但 allowlisted proxy 到 canonical upstream 的连接失败，exact Git fetch 失败 |

因此本机最终答案是：**现有两个已钉住引擎均不能满足冻结的 verifier
拓扑；不能启动生产 Git verifier，也不能运行 APPS 双正例。**

Docker 是按既有性质门进行的一次、且仅一次的替代引擎执行，不是放宽协议。它没有使用
`--network host`、wildcard listen、宿主 Git fetch、扩展 authority allowlist 或削弱探针。

## 2. Docker 引擎绑定

Docker 不是调用方自由选择的字符串，而是代码内白名单 profile：

| 字段 | 值 |
|---|---|
| profile ID | `docker-29.4.1` |
| executable | `/usr/bin/docker` |
| executable SHA-256 | `1fc0af13dcb8070408ce2ac4051b76f76ff0c63570bdaeeb6bd5b13b993d0249` |
| client version | `29.4.1` |
| server version | `29.4.1` |
| version-output SHA-256 | `7728e85580e079e17edb6b02fe937fe85727034c12a8d017a9efab6567e2733b` |
| invocation schema | `docker-cli-29.4-v1` |
| profile commit | `2bcc137` |

未知 profile、版本、可执行文件哈希或 invocation schema 均 fail closed。Podman 和
Docker 两个 profile 的结果均保留，避免只报告通过者的引擎轮盘赌。

## 3. Docker 一次性运行结果

### 3.1 已取得的真实观测

Docker 成功实例化了足以启动 fetch session 的双网络拓扑。容器内同一网络配置下得到：

| 探针 | 结果 | 定性 |
|---|---|---|
| canonical authority 经 proxy CONNECT | `HTTP/1.1 502 Bad Gateway` | 失败 |
| canonical host 当次解析出的 12 个 IP 直连 `:443` | 全部失败 | 仅佐证隔离机制 |
| `1.1.1.1:443` 直连 | 失败 | 仅佐证隔离机制 |
| 容器内 canonical host DNS | 解析失败 | 仅佐证隔离机制 |
| exact revision Git fetch | exit 128 | 失败 |
| blob OID | 未取得 | 失败 |
| blob content SHA-256 | 未取得 | 失败 |
| 独立 non-allowlisted authority live 403 | 未运行 | fetch session 失败后停止 |

直连探针的 proxy 环境变量已先清除。其结果只作为佐证；阻止默认 NAT 直连的机制承担
安全保证，不能把某次 IP 探针失败外推成所有地址永久不可达。

### 3.2 Proxy 审计日志

fetch session 接受了两个 socket，两条均完整记账：

```text
parsed_authorities = ["huggingface.co:443"]
accepted_connection_count = 2
allowed = 0
upstream_failed = 2
forbidden / malformed / client_aborted / handler_error = 0
upstream_connected = false
```

两次请求均为解析成功的 `CONNECT huggingface.co:443 HTTP/1.1`，proxy 均返回 502，
错误类别为 `OSError`。没有静默连接、未解析 authority 或第二 authority。

这不满足门的正向要求：canonical CONNECT 必须成功，exact fetch 和 blob 校验必须
成功，且另一个独立 session 必须现场证明非 allowlisted authority 返回 403。单元测试
中的 live allow/live reject 不能替代本次拓扑中缺失的 403 session。

### 3.3 终端 receipt 的权限异常

runner 的终端 receipt 首个 gate 记录为 `unexpected_preflight_error / PermissionError`：
proxy 产物按设计以 mode 0600 写出且由容器 UID 65534 持有，宿主 runner 在读取
`stable.json` 时被拒绝。运行后只用同一 pinned image、`--network none`、文件所有者
UID 65534 把产物 mode 改为可保存读取；内容未重写，之后才计算哈希。

这项仪器权限缺陷没有被第二次 Docker 运行掩盖。即使忽略它，已落盘的容器内结果也
明确不满足 frozen gate：CONNECT、fetch、blob 和 live-reject 四项不完整。因此裁决仍是
`NOT_IDENTIFIABLE_VERIFIER_TOPOLOGY`，而不是可修补后推断的 PASS。

## 4. Podman 三次与 Docker 一次的完整账本

| 执行 | 引擎 | 唯一变更/绑定 | 结局 |
|---|---|---|---|
| Podman V1 | 3.4.4 | 原冻结 topology | CNI internal 表示解析缺口 |
| Podman V2 | 3.4.4 | 仅加入 CNI internal fail-closed parser | `network connect --ip` 不支持 |
| Podman V3 | 3.4.4 | 仅去掉 egress `--ip` | internal static IP 被错误带入 egress 子网 |
| Docker | 29.4.1 | 加入 code-owned engine profile，冻结门不变 | proxy upstream 失败，exact fetch 失败 |

Podman 不做第四轮。Docker 不做第二轮。不会升级/安装运行时、设计第三种拓扑、回退宿主
fetch 或调整门槛来取得通过结果。

## 5. 未被放宽的性质

- verifier image 仍为 exact digest；
- proxy listen 仍为 internal network 上的 literal IP，不是 `0.0.0.0` 或 `::`；
- verifier 容器不获得默认外网 NAT；
- proxy authority 仍严格为预注册 canonical 单值；
- direct-IP、第三方 IP、DNS、live reject 五类探针未删除或改弱；
- candidate 执行 argv 仍精确包含相邻参数 `--network`, `none`；
- 无宿主 Git fetch、无凭据/secret mount、无候选代码执行；
- 无 provenance receipt、attestation、finding 或 promotion 激活；
- API 使用为零。

## 6. Docker 产物哈希

| Artifact | SHA-256 |
|---|---|
| terminal receipt | `da5b617c33da90ea842fe1f013f659a3403aaa31e035579e860fe6e41c0a1d4c` |
| proxy raw JSONL | `520f4df485216bae9fa06fa617a2760d17da5275fcaaa16c0e5b347eb13a126a` |
| proxy stable summary | `841dd2a44113ac069e1a47a34a7c35cca7dbccddfaa6d06e13534aa017cf6083` |
| fetch verifier result | `ec67f1324d98f64f936dc9fb7bb9eb267c44b4cff91dc9cd340552c17b0a3108` |
| preflight runner | `9ea97edd8846faa04309ab0176874961e30b88f75f90d09a4cf4eef08ddab1fb` |

详细的机器可读解释见
`docs/experiments/verifier_topology_preflight_docker_20260802/diagnostic_addendum.json`。

## 7. Claim boundary

本结果能证明：在这台宿主、这两个 code-owned engine profile、这道冻结门下，生产
verifier 拓扑不可识别；继续在本机做同类拓扑迭代没有研究收益。

本结果不能证明：

- 该拓扑在其他宿主或已预先钉住的兼容运行时上不可实现；
- Docker 的网络隔离一般不安全；
- proxy 的 allow/reject 门已在本次 Docker 拓扑完整通过；
- Git provenance verifier 已可采信；
- APPS 存在任何新的 confirmed finding。

若未来换到一台能支持冻结性质的机器，应从完整五探针开始独立执行；不得把本次部分
观测拼接成未来 PASS。本机当前实验线到此收口。
