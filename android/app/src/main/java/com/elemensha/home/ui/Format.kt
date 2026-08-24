package com.elemensha.home.ui

import kotlin.math.abs
import kotlin.math.roundToInt

/**
 * 한국 돈 단위 표기.
 *
 * 445200000 을 "445,200,000원"으로 보여주면 자릿수를 세게 된다.
 * "4억 4,520만원"이 사람이 실제로 쓰는 단위다.
 */
fun formatKrw(amount: Long?): String {
    if (amount == null) return "-"
    val sign = if (amount < 0) "-" else ""
    val value = abs(amount)
    val eok = value / 100_000_000
    val man = (value % 100_000_000) / 10_000
    return when {
        eok > 0 && man > 0 -> "$sign${eok}억 ${"%,d".format(man)}만원"
        eok > 0 -> "$sign${eok}억원"
        man > 0 -> "$sign${"%,d".format(man)}만원"
        else -> "$sign${"%,d".format(value)}원"
    }
}

/** 입력 필드용. 만원 단위 정수를 받는다. */
fun formatManwon(amount: Long?): String =
    if (amount == null) "" else "%,d".format(amount / 10_000)

fun parseManwonInput(text: String): Long {
    val digits = text.filter { it.isDigit() }
    return if (digits.isEmpty()) 0 else digits.toLong() * 10_000
}

fun formatPercent(ratio: Double?, decimals: Int = 1): String {
    if (ratio == null) return "-"
    return "%.${decimals}f%%".format(ratio * 100)
}

fun formatSignedPercent(ratio: Double?, decimals: Int = 1): String {
    if (ratio == null) return "-"
    val sign = if (ratio >= 0) "+" else ""
    return "$sign%.${decimals}f%%".format(ratio * 100)
}

/** 전용면적을 평으로. 분양면적이 아니라 전용 기준이라는 걸 화면에 함께 적는다. */
fun formatArea(sqm: Double?): String {
    if (sqm == null) return "-"
    val pyeong = (sqm / 3.3058 * 10).roundToInt() / 10.0
    return "전용 %.1f㎡ (%.1f평)".format(sqm, pyeong)
}

/** ISO 문자열에서 날짜만. 파싱 실패하면 원문을 그대로 돌려준다. */
fun formatDate(iso: String?): String {
    if (iso.isNullOrBlank()) return "-"
    return iso.take(10)
}
