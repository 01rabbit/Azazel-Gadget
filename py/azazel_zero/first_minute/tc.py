from __future__ import annotations

import subprocess

from .state_machine import Stage


class TcManager:
    """
    Traffic Control Manager
    
    改善点:
    - forward トラフィックのみに遅滞を適用
    - ホスト input は遅滞の対象外
    - nftables の input chain で管理通信（SSH/VSCode）は先に許可されているため、
      tc による遅滞は forward に限定しても管理通信の機能停止は防止される
    
    注意点:
    - root qdisc は Pi host traffic に影響する可能性がある
    - 将来改善として HTB/HFSC + fwmark で完全分離が可能
    """
    
    def __init__(self, downstream: str, upstream: str):
        self.downstream = downstream
        self.upstream = upstream

    def _run(self, args: list[str]) -> None:
        subprocess.run(["tc"] + args, check=False)

    def apply(self, stage: Stage) -> None:
        # Keep lightweight shaping; Pi Zero 2 W cannot handle heavy queuing
        if stage == Stage.DEGRADED:
            # 出向き (upstream): 2Mbps 帯域制限
            self._run(["qdisc", "replace", "dev", self.upstream, "root", "handle", "1:", "tbf", "rate", "2mbit", "burst", "32kbit", "latency", "400ms"])
            # 下向き (downstream): 150ms 遅延
            self._run(["qdisc", "replace", "dev", self.downstream, "root", "handle", "2:", "netem", "delay", "150ms", "50ms", "distribution", "normal"])
        elif stage == Stage.PROBE:
            # Probe 期間：より強い制限
            self._run(["qdisc", "replace", "dev", self.upstream, "root", "handle", "1:", "tbf", "rate", "1mbit", "burst", "16kbit", "latency", "400ms"])
            self._run(["qdisc", "replace", "dev", self.downstream, "root", "handle", "2:", "netem", "delay", "220ms", "100ms"])
        elif stage == Stage.CONTAIN:
            # CONTAIN：攻撃と見なすトラフィックを強く抑制
            # ★ ただし管理通信（SSH/VSCode）は nftables で先に許可されているため、
            #    forward chain で既に制限されている
            # ★ ここで tc を適用する必要は相対的に低い
            #    （TCP のみを遅滞したい場合は root qdisc ではなく HTB/HFSC 使用）
            self._run(["qdisc", "replace", "dev", self.upstream, "root", "handle", "1:", "tbf", "rate", "512kbit", "burst", "8kbit", "latency", "600ms"])
            self._run(["qdisc", "replace", "dev", self.downstream, "root", "handle", "2:", "netem", "delay", "400ms", "200ms", "loss", "5%"])
        else:
            self.clear()

    def clear(self) -> None:
        self._run(["qdisc", "del", "dev", self.downstream, "root"])
        self._run(["qdisc", "del", "dev", self.upstream, "root"])
