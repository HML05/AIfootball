# -*- coding: utf-8 -*-
"""深度学习分支 - 模型定义

两个模型：
1. MatchMLP      —— 纯表格特征的多层感知机(与 XGBoost 同输入，用于对照)
2. MatchGRUNet   —— 表格特征 + 主客队近 N 场序列的 GRU 编码器(共享权重，孪生结构)

GRU 分支的设计意图：让模型自己从"最近 N 场比赛的走势"里学出状态，
而不是依赖人工构造的滚动均值特征。
"""
import torch
import torch.nn as nn
from torch.nn.utils.rnn import pack_padded_sequence


class MatchMLP(nn.Module):
    """表格特征 MLP 基线"""

    def __init__(self, tab_dim: int, hidden: int = 128, dropout: float = 0.3):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(tab_dim, hidden), nn.ReLU(), nn.Dropout(dropout),
            nn.Linear(hidden, 64), nn.ReLU(), nn.Dropout(dropout),
            nn.Linear(64, 3),
        )

    def forward(self, x_tab, *_):
        return self.net(x_tab)


class MatchGRUNet(nn.Module):
    """表格特征 + 主客队近期序列(GRU) 的融合模型"""

    def __init__(self, tab_dim: int, seq_dim: int, hidden: int = 32,
                 tab_hidden: int = 64, head: int = 64, dropout: float = 0.3):
        super().__init__()
        # 主队与客队共享同一个编码器(孪生结构)，参数量小、不易过拟合
        self.gru = nn.GRU(seq_dim, hidden, num_layers=1, batch_first=True)
        self.tab = nn.Sequential(
            nn.Linear(tab_dim, tab_hidden), nn.ReLU(), nn.Dropout(dropout))
        self.head = nn.Sequential(
            nn.Linear(tab_hidden + hidden * 3, head), nn.ReLU(), nn.Dropout(dropout),
            nn.Linear(head, 3),
        )

    def encode(self, seq, lengths):
        ln = lengths.clamp(min=1)
        packed = pack_padded_sequence(seq, ln.cpu(), batch_first=True,
                                      enforce_sorted=False)
        _, hn = self.gru(packed)
        h = hn[-1]
        # 长度为 0(无历史)的样本，隐状态置零，避免读到 padding
        return h * (lengths > 0).float().unsqueeze(1)

    def forward(self, x_tab, h_seq, h_len, a_seq, a_len):
        hh = self.encode(h_seq, h_len)
        ha = self.encode(a_seq, a_len)
        z = torch.cat([self.tab(x_tab), hh, ha, hh - ha], dim=1)
        return self.head(z)


def build_model(kind: str, tab_dim: int, seq_dim: int = 12, **kw):
    if kind == "mlp":
        return MatchMLP(tab_dim, **kw)
    if kind == "gru":
        return MatchGRUNet(tab_dim, seq_dim, **kw)
    raise ValueError(f"未知模型类型: {kind}")


def count_params(model: nn.Module) -> int:
    return sum(p.numel() for p in model.parameters() if p.requires_grad)
