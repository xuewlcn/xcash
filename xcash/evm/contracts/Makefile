FORGE ?= forge
OPENZEPPELIN_CONTRACTS_VERSION := v5.6.1

.PHONY: all deps build test fuzz slither clean fixtures deploy verify

all: build fixtures

deps:
	@test -f lib/openzeppelin-contracts/package.json || \
		$(FORGE) install OpenZeppelin/openzeppelin-contracts@$(OPENZEPPELIN_CONTRACTS_VERSION) --no-git --shallow
	@python3 -c "import json; version=json.load(open('lib/openzeppelin-contracts/package.json'))['version']; assert version == '$(OPENZEPPELIN_CONTRACTS_VERSION)'[1:], f'openzeppelin-contracts version mismatch: {version}'"

build: deps
	$(FORGE) build --offline
	@mkdir -p artifacts
	@cp out/XcashVaultSlot.sol/XcashVaultSlot.json artifacts/XcashVaultSlot.json
	@python3 -c "import json; d=json.load(open('artifacts/XcashVaultSlot.json')); print(d['bytecode']['object'])" > artifacts/XcashVaultSlot.bin
	@python3 -c "import json; d=json.load(open('artifacts/XcashVaultSlot.json')); print(json.dumps(d['abi'], indent=2, ensure_ascii=False))" > artifacts/XcashVaultSlot.abi.json
	@cp out/XcashVaultSlotFactory.sol/XcashVaultSlotFactory.json artifacts/XcashVaultSlotFactory.json
	@python3 -c "import json; d=json.load(open('artifacts/XcashVaultSlotFactory.json')); print(d['bytecode']['object'])" > artifacts/XcashVaultSlotFactory.bin
	@python3 -c "import json; d=json.load(open('artifacts/XcashVaultSlotFactory.json')); print(json.dumps(d['abi'], indent=2, ensure_ascii=False))" > artifacts/XcashVaultSlotFactory.abi.json

test: deps
	$(FORGE) test --offline -vvv

# 只跑 Fuzz 属性测试（testFuzz_ 前缀），调高 runs 加大随机覆盖。
fuzz: deps
	FOUNDRY_FUZZ_RUNS=10000 $(FORGE) test --offline --match-test testFuzz -vvv

# Slither 静态安全扫描。需先安装：uv tool install slither-analyzer
slither: deps
	@command -v slither >/dev/null 2>&1 || \
		{ echo "slither 未安装：uv tool install slither-analyzer（或 pipx install slither-analyzer）"; exit 1; }
	slither . --config-file slither.config.json

fixtures: deps
	@mkdir -p ../tests/fixtures
	$(FORGE) script scripts/DumpXcashVaultSlotFixtures.s.sol --tc DumpXcashVaultSlotFixtures --offline

clean:
	rm -rf out/ cache/

# ===== 链上部署 / 验证 =====
# 用法： make deploy <chainid>     make verify <chainid>
#   chainid: 1 = Ethereum    56 = BSC    11155111 = Sepolia
# 凭据从 .env 自动读取（.env 已 gitignore，切勿提交）：
#   PRIVATE_KEY=0x...        部署私钥
#   ETHERSCAN_API_KEY=...    源码验证 key（Etherscan V2 单 key 全链通用）
# deploy / verify 均一次处理实现合约 + 工厂两个合约。

# 取目标后面的第一个词当 chain id： make deploy 56 → CHAIN=56
CHAIN := $(word 2,$(MAKECMDGOALS))
# 让裸 chain id 成为空操作目标，避免 make 报 "No rule to make target '56'"
%:
	@:

# 各链公共 RPC（取自 chainlist，无需 key）
RPC_1        := https://ethereum-rpc.publicnode.com
RPC_56       := https://bsc-rpc.publicnode.com
RPC_11155111 := https://ethereum-sepolia-rpc.publicnode.com
RPC          := $(RPC_$(CHAIN))

# BSC 走 legacy gas，规避 EIP-1559 估价异常
EXTRA_56 := --legacy
EXTRA    := $(EXTRA_$(CHAIN))

# 部署地址从部署脚本的 EXPECTED_* 解析（唯一真源）。源码/编译参数变更会让确定性
# CREATE2 地址漂移，此处自动跟随，绝不在 Makefile 里再硬编码一份，避免与
# scripts/DeployXcashVaultSlot.s.sol、evm/constants.py 三处不一致。
IMPL_ADDR    := $(shell grep -oE 'EXPECTED_IMPLEMENTATION = 0x[0-9a-fA-F]{40}' scripts/DeployXcashVaultSlot.s.sol | grep -oE '0x[0-9a-fA-F]{40}')
FACTORY_ADDR := $(shell grep -oE 'EXPECTED_FACTORY = 0x[0-9a-fA-F]{40}' scripts/DeployXcashVaultSlot.s.sol | grep -oE '0x[0-9a-fA-F]{40}')

deploy: deps
	@test -n "$(RPC)" || { echo "用法: make deploy <chainid>（支持 1 / 56 / 11155111）"; exit 1; }
	@set -a; . ./.env; set +a; test -n "$$PRIVATE_KEY" || { echo "❌ .env 缺少 PRIVATE_KEY"; exit 1; }; \
		echo "▶ 部署到 chain $(CHAIN)  RPC=$(RPC)"; \
		$(FORGE) script scripts/DeployXcashVaultSlot.s.sol --tc DeployXcashVaultSlot --rpc-url $(RPC) --private-key "$$PRIVATE_KEY" --broadcast $(EXTRA) -vvv

verify: deps
	@test -n "$(RPC)" || { echo "用法: make verify <chainid>（支持 1 / 56 / 11155111）"; exit 1; }
	@test -n "$(IMPL_ADDR)" -a -n "$(FACTORY_ADDR)" || { echo "❌ 无法从 scripts/DeployXcashVaultSlot.s.sol 解析 EXPECTED_* 地址"; exit 1; }
	@set -a; . ./.env; set +a; test -n "$$ETHERSCAN_API_KEY" || { echo "❌ .env 缺少 ETHERSCAN_API_KEY"; exit 1; }; \
		echo "▶ 验证 chain $(CHAIN)：impl=$(IMPL_ADDR)  factory=$(FACTORY_ADDR)"; \
		$(FORGE) verify-contract $(IMPL_ADDR) src/XcashVaultSlot.sol:XcashVaultSlot --chain $(CHAIN) --etherscan-api-key "$$ETHERSCAN_API_KEY" --watch; \
		$(FORGE) verify-contract $(FACTORY_ADDR) src/XcashVaultSlotFactory.sol:XcashVaultSlotFactory --chain $(CHAIN) --etherscan-api-key "$$ETHERSCAN_API_KEY" --constructor-args $$(cast abi-encode "constructor(address)" $(IMPL_ADDR)) --watch
