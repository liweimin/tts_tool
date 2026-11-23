import unittest

from tts_reader import translator


class TestTranslatorLanguageDetection(unittest.TestCase):
    def test_chinese_text_with_technical_terms(self):
        # 用户的两段问题文本（应为 False，不翻译，保持原汁原味中文直接朗读）
        text1 = (
            "我从 2026 年早些时候开始接触评测工作，过去半年给 Tabbit Browser、"
            "Offloop、Persom 及一些朋友的创业项目做过评测相关工作或进行过交流，"
            "这些项目大部分类似一个 通用 Agent 的形态。"
        )
        text2 = (
            "这篇文章是 2026 年 10 月开始写的，主要分享我做 General Agent System "
            "评测工作时的一些经验（后文把 General Agent System 简写成 Agent）。"
        )
        self.assertFalse(translator.is_mostly_english(text1))
        self.assertFalse(translator.is_mostly_english(text2))

    def test_chinese_technical_mixed(self):
        # 常见中文技术混排
        case1 = "推荐使用 Visual Studio Code 打开这个仓库，并运行 npm run dev 进行调试。"
        case2 = "这个项目基于 React 和 Vue3 架构开发，遇到了一个 Memory Leak 问题。"
        case3 = "今天天气真好，出去散步。"
        case4 = "用 Python 写了一个简单的 TTS 工具。"
        self.assertFalse(translator.is_mostly_english(case1))
        self.assertFalse(translator.is_mostly_english(case2))
        self.assertFalse(translator.is_mostly_english(case3))
        self.assertFalse(translator.is_mostly_english(case4))

    def test_pure_english(self):
        en1 = "The weather is very nice today, let us go for a walk in the park."
        en2 = "Artificial intelligence and large language models are transforming modern software development."
        self.assertTrue(translator.is_mostly_english(en1))
        self.assertTrue(translator.is_mostly_english(en2))

    def test_english_with_few_chinese_noises(self):
        # 英文截图带噪点汉字
        text1 = "TypeError: Cannot read properties of undefined (reading map) at line 42. 点击重试"
        # 英文邮件带简短署名
        text2 = "Sender: 张三\nHello team, please review this pull request as soon as possible. Thank you!"
        self.assertTrue(translator.is_mostly_english(text1))
        self.assertTrue(translator.is_mostly_english(text2))


if __name__ == "__main__":
    unittest.main()
