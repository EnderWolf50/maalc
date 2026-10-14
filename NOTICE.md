# 第三方聲明

## MaaPracticeBoilerplate

專案骨架（`assets/interface.json` 的結構、`agent/main.py` 的 AgentServer 進入點、`maatools.config.mts`、`tools/` 的 OCR 模型與安裝腳本）參考 [MaaPracticeBoilerplate](https://github.com/MaaXYZ/MaaPracticeBoilerplate) 改寫，依其 MIT 授權保留以下聲明：

```
MIT License

Copyright (c) 2024 MaaXYZ

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## OCR 模型 ppocr_v6/small

`assets/resource/base/model/ocr/` 的模型由 `tools/fetch_ocr.py` 從 [MaaCommonAssets](https://github.com/MaaXYZ/MaaCommonAssets/tree/main/OCR/ppocr_v6/small) 下載，不放進 repo。模型出自 [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) 的 PP-OCRv6，採 [Apache-2.0](https://www.apache.org/licenses/LICENSE-2.0) 授權。

## Limbus Company 遊戲素材

`assets/resource/base/image/` 的模板與 `tests/screens/` 的測試截圖取自 Limbus Company 的遊戲畫面，著作權屬於 © Project Moon，不在本專案的 MIT 授權範圍內。測試截圖中的 UID 與帳號已遮蔽。
