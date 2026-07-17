# ecc-vsdd Skills and Agents Reference

## Model routing policy

| Skill / responsibility | Pinned agent | Model | Effort |
| --- | --- | --- | --- |
| `vsdd-run` | `vsdd-orchestrator` | Fable | `high` |
| `vsdd-steering` | `vsdd-steering-worker` | Opus | `xhigh` |
| `vsdd-init` | `vsdd-init-worker` | Haiku | `low` |
| `vsdd-requirements` | `vsdd-requirements-worker` | Opus | `xhigh` |
| `vsdd-review-requirements` | `vsdd-requirements-reviewer` | Opus | `xhigh` |
| `vsdd-design` | `vsdd-design-worker` | Opus | `xhigh` |
| `vsdd-tasks` | `vsdd-tasks-worker` | Sonnet | `high` |
| `vsdd-review-plan` | `vsdd-plan-reviewer` | Opus | `xhigh` |
| `vsdd-impl` plan / implementation | `vsdd-implementation-driver` | Sonnet | `ultracode` |
| implementation plan review | `vsdd-implementation-workflow-reviewer` | Opus | `xhigh` |
| code review | `vsdd-code-reviewer` | Opus | `xhigh` |
| security review | `vsdd-security-reviewer` | Opus | `xhigh` |
| ordinary remediation | `vsdd-remediation-worker` | Sonnet | `high` |
| complex remediation | `vsdd-implementation-driver` | Sonnet | `ultracode` |
| `vsdd-pr` | `vsdd-pr-worker` | Sonnet | `medium` |
| `vsdd-workflow` bookkeeping | `vsdd-status-worker` | Haiku | `low` |

Plugin agentは`agents/`に同梱します。直接Skillを実行した場合も同じagentへ委譲します。`inherit`、fallback、`max`、worker Fableは禁止です。

## `vsdd-run`

```text
/ecc-vsdd:vsdd-run start <request-or-slug> [source] [--mode auto|standard] [--base ref] [--until review|pr]
/ecc-vsdd:vsdd-run resume <slug> [source] [--until pr]
/ecc-vsdd:vsdd-run status <slug>
/ecc-vsdd:vsdd-run cancel <slug>
/ecc-vsdd:vsdd-run cleanup <slug>
```

再開可能な状態機械です。Fableは固定fieldを読んで次phaseを選び、専用workerを起動します。成果物を自分で作りません。

`start`は`operation: bootstrap`としてbundled runtimeの`bootstrap` commandだけを実行します。実際のrepository default（または明示`--base`）を検出し、base ref/branch/SHAを保存してから`vsdd/<slug>`と専用integration worktreeを作り、この時点のfeature specを`bootstrap_status: READY`の`run-state.json`だけにします。Phase 0より前なのでこのinvocationはSteeringを要求せず終了します。Steering後の別`operation: phase` Initが正確なbootstrap identityを検証してskeletonを作り、`CONSUMED`へ遷移します。曖昧でも`main`を仮定しません。`resume`はhashとcommitを再検証し、staleなphaseと下流を無効化します。source引数を付けたresumeは既存skeletonを保ったままsourceを更新し、Requirements以降を再実行します。terminal gateは要求境界でtop-level `COMPLETE`を保存し、Review完了後の明示`--until pr`だけが`extend` gateでPhase 9へ再オープンします。

Skill frontmatterの`PreToolUse` hookはFableに対して次を機械的に拒否します。

- Write / Edit / Notebook edit
- bundled launcher以外のBash
- 未固定agent
- per-invocation model overrideと混在sessionのglobal model固定
- Fable `high`以外のeffort
- orchestrator agent外でのfull-run mutation

## Phase Skills

### `vsdd-steering`

```text
/ecc-vsdd:vsdd-steering [--force] [--dry-run]
```

`_steering/`を生成またはrefreshします。自動runではrepository fingerprintがmissing/staleの場合だけOpus `xhigh`を起動します。`tech.md`はstack、design viewpoints、conventions、verification commandsの正本です。

### `vsdd-init`

```text
/ecc-vsdd:vsdd-init <slug> [source-url] [--mode auto|standard]
```

Haiku `low`がspec skeleton、source、progress、change logを作成します。Steeringの作成は行わず、Opusによるcurrent状態を要求します。全自動`start`では先にintegration branch/worktreeと`run-state.json`だけをmanaged bootstrapし、Phase 1ではそれを上書きせず消費します。

無人runではsourceとrepository evidenceから値を導出し、質問やoverwrite確認を行いません。`--update-source`では既存specへsourceだけを保存し、取得失敗時はblockします。

### `vsdd-requirements`

```text
/ecc-vsdd:vsdd-requirements <slug>
```

Opus `xhigh`がEARS形式の`REQ-NNN`とbinaryな受入条件を作成します。無人runでは従来の7項目インタビューをソースから自動導出して`Elicitation Basis`へ記録します。可逆な技術的仮定は記録できますが、製品、security、compatibility、data-loss、destructive decisionはblockします。

### `vsdd-review-requirements`

```text
/ecc-vsdd:vsdd-review-requirements <slug>
```

新規Opus `xhigh`がdisk-only contextでEARS、曖昧さ、testability、completeness、feasibility、term driftを確認します。Requirements authorとは別sessionです。

### `vsdd-design`

```text
/ecc-vsdd:vsdd-design <slug>
```

Opus `xhigh`がapproved REQ、Steering viewpoints、ADRを満たす`design.md`を作成します。ECC planning capabilityを使う場合もこのOpus worker内で実行します。

### `vsdd-tasks`

```text
/ecc-vsdd:vsdd-tasks <slug>
```

Sonnet `high`が`TASK-NNN`を作成し、REQとDesignへ紐付けます。TASKはwhatとverificationを定義し、dependency、parallel group、worktreeは定義しません。これらはPhase 7 Dynamic Workflowが決定します。

Plan Review前のdeterministic gateは`tasks.md`見出しと`progress.md` Tasks tableのID集合が重複なく完全一致することを要求します。

### `vsdd-review-plan`

```text
/ecc-vsdd:vsdd-review-plan <slug>
```

新規Opus `xhigh`がRequirements、Design、Tasksをまとめてreviewし、A〜Iのtraceabilityとviewpoint coverageを検証します。1件でも❌、またはCRITICAL/HIGHがあれば`REVISE`です。

### `vsdd-impl`

```text
/ecc-vsdd:vsdd-impl <slug>
```

TASK単位引数は使用しません。bundled launcherが独立Sonnet main sessionを次の条件で起動します。

```text
--model sonnet
--effort ultracode
CLAUDE_CODE_SUBAGENT_MODEL=sonnet
```

custom agent frontmatterには`ultracode`を書かず、launcherだけがセッション起動時に指定します。これによりfrontmatterの通常effort値がultracodeを上書きする経路をなくし、hookは実効推論値`xhigh`を検証します。

最初のDynamic Workflowは`implementation-workflow.md`だけを作成し、コードを変更しません。launcher自身がphase preflight、plugin manifest依存のchild引き継ぎ、session bindingを行います。長時間処理はlauncher-owned detached supervisorへ移し、Fableはshell backgroundを使わずforegroundの`wait --wait-seconds 45`をterminal結果まで反復します。新規Opus `xhigh`がPASSした後、そのworkflowをimmutableに保ったまま同じSonnet sessionをresumeして全TASKを実装します。attempt、TDD証跡、検証結果、正確な`TASK-to-SHA Mapping`は`implementation-ledger.md`へ保存し、runtimeのTASK別begin/finish counterにもPASS/FAILを記録します。

### `vsdd-review`

```text
/ecc-vsdd:vsdd-review <slug>
```

別々の新規Opus `xhigh`を同じfull commit SHAへ起動します。

- `vsdd-code-reviewer` → `review-results/code-review.md`
- `vsdd-security-reviewer` → `review-results/security-review.md`

相互にcontextやfindingを渡しません。どちらかにCRITICAL/HIGHがあればPRをblockします。

### `vsdd-pr`

```text
/ecc-vsdd:vsdd-pr <slug>
```

Sonnet `medium`がREQ → Design → TASK → commit表、test plan、verification、review summaryを含むPRを作成します。実際のURL/numberとbase/head/target SHAを`pr-result.json`へ保存し、runtime snapshotがcurrent `HEAD`を検証します。

- CRITICAL/HIGHあり: 作成しない
- MEDIUM/manual follow-upあり: Draft
- どちらもなし: Ready

### `vsdd-workflow`

```text
/ecc-vsdd:vsdd-workflow [slug]
```

状態dashboardです。Haiku `low`が必要に応じてhash、commit、attempt、verdict、worktree、session IDを更新します。要件、設計、実装、review、PR本文は作成しません。

## Structured review artifact

すべてのreviewは次のfrontmatterを必須とします。

```yaml
---
review_type: requirements|plan|implementation-workflow|code|security
target_commit: <full-sha-or-N/A>
verdict: PASS|REVISE|BLOCKED
critical: <integer>
high: <integer>
medium: <integer>
low: <integer>
remediation_mode: none|standard|workflow
reviewer_model: opus
reviewer_effort: xhigh
review_attempt: <1..3>
---
```

Fableはこのfieldだけでgate遷移します。review本文の再評価やseverity変更は行いません。Status runtimeがreview前にatomic attempt numberを発行し、frontmatter、Opus/xhigh、severity整合性、単調なattempt、target commitを検証してsnapshotします。snapshotのないreviewを前段PASSとして認めず、同じattempt番号でreportを差し替えることもできません。

## Retry limits

| 対象 | 上限 |
| --- | --- |
| Requirements review | initial + 2 revisions/reviews |
| Plan review | initial + 2 revisions/reviews |
| Implementation Workflow review | initial + 2 revisions/reviews |
| 各TASK | initial + 2 retries |
| Code/Security remediation | initial review + 2 remediation/re-review rounds |

上限到達後は`VSDD RUN BLOCKED`です。FableやOpusが作業を引き継いだりgateをwaiveしたりしません。

## Bundled runtime files

| File | Role |
| --- | --- |
| `scripts/vsdd-model-guard.py` | pinned model / effort、model override、Fable control-plane toolのruntime guard |
| `scripts/vsdd-launch-worker.py` | independent Sonnet ultracode sessionの起動／resume |
| `scripts/vsdd-runtime-state.py` | bootstrap/base検出、artifact hash無効化、phase/review/Steering/TASK/commitのdeterministic gate |
| `skills/vsdd-run/references/model-routing.md` | model / effort正本 |
| `skills/vsdd-run/references/run-state-contract.md` | state、hash、invalidation、retry正本 |
| `skills/vsdd-run/references/review-contract.md` | review schemaとseverity正本 |
| `skills/vsdd-run/references/implementation-contract.md` | Dynamic Workflow、TDD、commit、remediation正本 |
| `skills/vsdd-run/references/runtime-contract.md` | 無人context、phase preflight、source update、TASK integrity正本 |
