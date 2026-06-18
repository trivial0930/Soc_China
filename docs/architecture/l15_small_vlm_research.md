# L1.5 端侧小 VLM 选型调研（RDK X5 CPU）

日期：2026-06-17 ｜ 方法：deep-research(5 路检索→抓取→对抗验证)，综合由 Claude 补全(研究中途撞会话额度,部分 claim 仅单源已抓取未投票,下方标注)。

## 问题
给 L1.5 端侧轻认知层选一个 **1–3B、中文能力够、能在 RDK X5 本机 CPU 跑** 的 VLM:读一张证据图 + 短结构化事件文本 → 出小 JSON 判断。RDK X5 = 8×A55 CPU(无 GPU)、Bayes-e BPU(~10TOPS,定图 CNN)、8GB RAM、离线。服务层 OpenAI 兼容(llama.cpp `llama-server` / Ollama),客户端代码零改。

## 关键结论(TL;DR)
1. **BPU 跑不了这类生成式 VLM（端到端）** → **纯 CPU 是务实路径**。BPU 至多能加速视觉编码器(研究性工作,非开箱)。
2. **能在 llama.cpp 主线跑的中文候选 = Qwen2-VL-2B / Qwen2.5-VL-3B / InternVL2.5-1B/2B**(均需配套 `mmproj` 视觉投影 GGUF)。**InternVL2(非 2.5)、InternVL3-hf 变体不支持**。
3. **真正瓶颈 = 视觉 prefill 的 token 数,不是参数量**。这决定 A55 CPU 上的延迟:
   - **Qwen2-VL 一张图 ≈ 16k 视觉 token**(原生动态分辨率,token 爆炸)→ A55 上会很慢;
   - **InternVL2.5 每 448 切片 = 256 token**,切片数(`n_max`)可调 → 限成 1 片 ≈ 256 token,**可控、轻**;
   - **SmolVLM 一张图 ≈ 1.2k token**(9× 压缩),prefill 比 Qwen2-VL-2B 快 3.3–4.5×、生成快 7.5–16× —— **但 SmolVLM 中文弱**,不选。
4. **务实选型**:
   - **主选 = InternVL2.5-2B**:中文强(InternViT-300M + InternLM2.5-1.8B)、llama.cpp 主线支持、**视觉 token 可压到 256(限 1 切片)→ A55 上 prefill 最轻**、内存小(Q4 ~1.2GB + 0.3B 编码器)。中文/延迟/可部署性三者最均衡。
   - **备选 = Qwen2.5-VL-3B-Instruct**:中文最好、主线支持、Q4 ~1.8GB + mmproj ~1.3GB;**但必须狠压输入分辨率**(用 `min_pixels`/`max_pixels` 把视觉 token 限到几百),否则 16k-token prefill 在 A55 上几十秒。质量优先时用它。
   - 更小 = InternVL2.5-1B(0.9B:InternViT-300M + Qwen2.5-0.5B):最快最省,但 0.5B 语言塔判断力弱,留作"实在太慢"的降级档。
5. **未决变量 = A55 实测 tok/s**:研究能确认"架构跑得通",但 8×A55@1.5GHz 的真实 decode/prefill 速度需**上板实测**。预估:2–3B Q4 decode ~几 tok/s、prefill 数十 tok/s → 限好视觉 token 后单次有望几秒~十几秒;不限就 30s+。**这是上板第一件要量的事**。

## 候选对比

| 模型 | 参数 | 中文 | llama.cpp 主线 | 视觉 token/图 | Q4 内存(LLM+mmproj) | 评 |
|---|---|---|---|---|---|---|
| **InternVL2.5-2B** | 2.2B | 强 | ✅(2.5/3,非 2/hf) | **256×切片(可限1)** | ~1.2G + 编码器0.3B | **主选** |
| Qwen2.5-VL-3B | 3B | 最强 | ✅ | 高(需压分辨率) | ~1.8G + ~1.3G | 备选(质量优先) |
| Qwen2-VL-2B | 2B | 强 | ✅ | **~16k(爆炸)** | ~1.0G + 1.33G | ❌ token 太多,弃 |
| InternVL2.5-1B | 0.9B | 中 | ✅ | 256×切片 | 最小 | 降级档(太慢时) |
| SmolVLM-2B | 2.2B | **弱** | ✅ | ~1.2k(最省) | 小 | ❌ 中文弱 |
| MiniCPM-V 2.x | 2.8–8B | 强 | Ollama 可 | 高 | 大 | 偏大,次选 |
| Moondream2 / PaliGemma | — | 弱 | ✅/部分 | — | — | ❌ 中文弱 |

## BPU 能不能帮忙
- RDK Model Zoo 四类(分类/检测/分割/"Large Models"占位),**无生成式 VLM/LLM**;多模态仅 CLIP 编码器、YOLOWorld。
- `hobot_llm`(官方 on-BPU LLM demo)是 **RDK X3 + 纯文本**,非 X5、非 VLM。
- OpenExplorer/`hb_mapper` 吃 ONNX(opset10/11)/Caffe 定图;不支持的算子回落 CPU(VLM 转 ONNX 会大量回落)。
- **结论:BPU 端到端跑 VLM 无开箱路径;纯 CPU(llama.cpp)是路。** 想压榨可探索"视觉编码器(InternViT-300M)上 BPU、LLM 解码 CPU",属研究项,非竞赛期该碰的。

## 上板落地建议(供 L1.5 bring-up)
1. **先装 llama.cpp(较新版,主线已含 Qwen2.5-VL/InternVL2.5 的 mtmd)**,aarch64 CPU 编译;`llama-server` OpenAI 兼容,`tier.fast.vlm_base_url=http://localhost:8080/v1`。
2. **先上 InternVL2.5-2B Q4_K_M + mmproj**,启动**限单切片/小图**(证据图先 resize 到 ~448px)。
3. **第一件事:实测单次延迟**(冷/热、纯文本 vs 带图)。目标几秒;若 prefill 仍数十秒:① 再降图分辨率/切片;② 退 InternVL2.5-1B;③ 退"L1.5 纯文本"(不喂图,只读事件文本初判)或干脆 L1.5=规则档、靠 L2。
4. 改 `cognition.yaml` 的 `tier.fast.vlm_model` 从占位 `qwen2-vl:2b` → 实际选定(InternVL2.5-2B);阈值 `escalate_below_confidence` 真机调。

## 引用(主要源)
- llama.cpp 多模态支持表 & mtmd README(Qwen2-VL/2.5-VL、InternVL2.5/3、SmolVLM、mmproj/Q4_K_M):github.com/ggml-org/llama.cpp `docs/multimodal.md`、`tools/mtmd/README.md`(✅验证 3-0)
- Qwen2.5-VL 技术报告(三尺寸,3B 面向 edge):arxiv.org/pdf/2502.13923(✅3-0)
- InternVL2.5 报告(1B=0.9B/2B=2.2B 组成、448 切片=256 token、OpenCompass 分):arxiv.org/pdf/2412.05271(单源)
- SmolVLM blog(81 token/patch、prefill 3.3–4.5× 快于 Qwen2-VL-2B):huggingface.co/blog/smolvlm(单源)
- Qwen2-VL mmproj f16=1.33GB:github.com/ggml-org/llama.cpp/issues/18881(单源)
- Qwen2.5-VL-3B GGUF Q4 ~1.74–1.94GB + 需 mmproj:huggingface.co/Mungert/Qwen2.5-VL-3B-Instruct-GGUF(单源;其"需 fork"说法疑过时,与主线支持表冲突——以主线表为准,用较新 llama.cpp)
- RDK Model Zoo / hobot_llm / OpenExplorer FAQ(BPU 无生成式 VLM、X3-only、定图回落 CPU):github.com/D-Robotics/rdk_model_zoo、github.com/HorizonRDK/hobot_llm、developer.d-robotics.cc FAQ/toolchain(单源,多源一致)
