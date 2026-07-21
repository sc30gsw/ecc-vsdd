# ecc-vsdd release checklist

同じRC commitと同じmarketplace install payloadを、途中で作り直さずに全gateへ通す。チェックが1つでも未完了ならpublicationしない。

## 1. Release candidateを固定

- [ ] release branchのcheckoutがcleanで、base commitとremote default branchを記録した
- [ ] `.claude-plugin/plugin.json`と`skills/vsdd-run/SKILL.md`のversionが一致する
- [ ] `CHANGELOG.md`の日付・version・breaking boundaryが正しい
- [ ] repository ownerがlicenseを選択し、`LICENSE`とmanifest `license`が一致する
- [ ] `git diff --check`と全JSON parseが成功する
- [ ] RC commit SHAと`git archive` SHA-256をrelease evidenceへ記録した

## 2. Local/CI gate

- [ ] Linux / Python 3.10、3.13のCIが成功する
- [ ] macOS / Python 3.10、3.13のCIが成功する
- [ ] `python -m py_compile scripts/*.py`が成功する
- [ ] unit/integration testが全件成功する
- [ ] subprocessを含むoverall line coverageが80%以上
- [ ] `scripts/*.py`各ファイルのline coverageが80%以上
- [ ] `claude plugin validate . --strict`が成功する

## 3. 公式仕様照合

- [ ] Claude Code公式のPlugin、Hooks、Subagents、Permissions、CLI、Dynamic Workflows仕様と実装を照合した
- [ ] `--add-dir`、permission mode継承、plugin agent制約、`claude -p`の無人実行条件を確認した

## 4. 配布物を新規install

- [ ] 空の`CLAUDE_CONFIG_DIR`へrepository/marketplace sourceからinstallした（`--plugin-dir`は不可）
- [ ] dependency `ecc`がmanifestから自動解決された
- [ ] plugin listのversionがRC versionと一致する
- [ ] install cacheに15 agents、全skills、hooks、scripts、manifestが存在する
- [ ] source RC archiveとinstall cacheの対象payload hashが一致する

## 5. Fresh-install Review E2E

- [ ] cleanな新規Git repositoryと自己完結した詳細briefを用意した
- [ ] Fable `high` orchestratorからexact `start ... --until review`を1回送った
- [ ] Steering→Init→Requirements→Design→Tasks→Dynamic Workflow TDD→全Opus reviewが無人完走した
- [ ] agent/model/effort routingとattempt/commit/artifact hashを`run-state.json`で確認した
- [ ] Review証拠がcurrent target commitと一致した
- [ ] Code/Security reviewのCRITICAL/HIGHがあればSonnet remediation後にfresh Opus pairがPASSした
- [ ] terminal stateが`status: COMPLETE`、`reached: review`
- [ ] E2E中に外部push/GitHub mutationが発生していない

## 6. Promote and publish

- [ ] E2Eを通したRC commitから内容変更なしで`1.0.0`へversionだけを更新した
- [ ] version変更commitへlocal validationを再実行した
- [ ] signed/annotated `v1.0.0` tagが最終commitを指す
- [ ] tag archiveのpayload hashが検証済みartifactと一致する
- [ ] tagをpushし、GitHub release notesを`CHANGELOG.md`から作成した
- [ ] 空のconfigへ`1.0.0`をinstallし、version/component inventoryをsmoke testした
- [ ] rollback対象versionと手順をrelease evidenceへ記録した
