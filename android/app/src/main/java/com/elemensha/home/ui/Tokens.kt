package com.elemensha.home.ui

import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp

/**
 * 화면 전체가 쓰는 값의 원본.
 *
 * 규칙 셋. CABINET 에서 가져온 방식이고, 색만 이 앱 것으로 바꿨다.
 *
 * 1) 색이 아니라 빛으로 만든다. 면은 단색이 아니라 위쪽에 밝은 모서리를
 *    한 줄 넣어 종이가 떠 있게 만든다. 광택은 배경에, 대비는 숫자에.
 * 2) 뜻이 없는 색은 쓰지 않는다. 이 앱의 색 셋은 로고 큐브의 세 면에서
 *    그대로 왔고, 각각 하나의 뜻만 갖는다.
 *      빨강  - 돈을 잃을 수 있는 것 (인수 보증금, 농취증, 마감 임박)
 *      초록  - 자료로 확인된 것 (입찰 가능, 명도 부담 없음, 할인폭)
 *      파랑  - 누를 수 있는 것 (동작, 선택)
 *    호박색은 하나 더 있는데 '출처를 우리가 확인하지 못한 값'에만 쓴다.
 *    이 넷 말고는 전부 먹색 계조다.
 * 3) 3초 안에 읽혀야 한다. 물건 하나에 붙는 경고가 여섯 줄인데 전부
 *    같은 크기 같은 회색이면 아무것도 안 읽힌다. 위험은 칸으로 묶고
 *    나머지는 작게 내린다.
 */
object Tone {
    /** 로고 큐브 세 면에서 뽑은 값. 원색은 글자로 쓰면 흐려서 어둡게 한 짝을 같이 둔다. */
    val Red = Color(0xFFBD2033)
    val RedDeep = Color(0xFF8E1424)
    val RedWash = Color(0xFFFCEDEF)

    val Green = Color(0xFF7CBE38)
    val GreenDeep = Color(0xFF3F7A1B)
    val GreenWash = Color(0xFFEFF6E8)

    val Blue = Color(0xFF45A1E4)
    val BlueDeep = Color(0xFF1F6FAF)
    val BlueWash = Color(0xFFEAF3FB)

    /** 출처 미검증. 위험(빨강)과 구분돼야 해서 따로 둔다. */
    val Amber = Color(0xFF8F5A0E)
    val AmberWash = Color(0xFFFDF3E3)
}

/** 밝은 화면의 면과 글자. */
object Paper {
    val P50 = Color(0xFFFDFEFE)
    val P75 = Color(0xFFF3F6F8)
    val P100 = Color(0xFFE9EEF2)
    val P200 = Color(0xFFDAE1E8)

    val Ink = Color(0xFF16202B)
    val Ink2 = Color(0xFF45566B)
    val Muted = Color(0xFF6B7B8E)

    val Line = Color(0x1F16202B)
    val Edge = Color(0xF0FFFFFF)
}

/** 로고 바탕의 흑연. 상단 띠와 중요한 동작에 쓴다. */
object Graphite {
    val G900 = Color(0xFF0B1016)
    val G800 = Color(0xFF141C25)
    val G700 = Color(0xFF1E2935)
    val G600 = Color(0xFF2C3A49)

    val OnDark = Color(0xFFEEF3F7)
    val OnDarkMuted = Color(0xFF9DAEBF)
}

/** 어두운 화면. 종이를 뒤집는 게 아니라 흑연을 바탕으로 삼는다. */
object PaperDark {
    val Surface = Color(0xFF151C25)
    val SurfaceHigh = Color(0xFF1C2531)
    val Background = Color(0xFF0D131A)
    val Ink = Color(0xFFE7EDF3)
    val Ink2 = Color(0xFFB3C1CF)
    val Muted = Color(0xFF8494A5)
    val Line = Color(0x2EFFFFFF)
}

object Dim {
    /** 손가락이 닿는 것의 최소 높이. 이보다 작은 조작 요소를 만들지 않는다. */
    val Tap = 48.dp
    val TapSmall = 40.dp

    val CardRadius = 14.dp
    val ChipRadius = 999.dp
    val BandRadius = 16.dp

    /** 카드 왼쪽에 세우는 뜻 있는 색 띠의 두께. */
    val AccentBar = 4.dp

    val ScreenPad = 14.dp
    val CardPad = 13.dp
    val Gap = 9.dp
    val GapTight = 5.dp
}

/** 뜻 있는 색 한 벌. 글자색·바탕색·띠색이 항상 같이 움직이게 묶어 둔다. */
data class ToneSet(val fg: Color, val wash: Color, val bar: Color)

enum class Meaning { Neutral, Good, Caution, Danger, Action }
