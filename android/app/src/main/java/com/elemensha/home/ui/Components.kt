package com.elemensha.home.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * 화면이 공통으로 쓰는 조각들.
 *
 * 여기 없는 모양을 화면에서 새로 만들지 않는다. 같은 뜻이 화면마다 다른
 * 크기와 색으로 나오면 사용자는 그것을 다른 뜻으로 읽는다.
 */

private fun Color.isDarkGround(): Boolean =
    (0.299f * red + 0.587f * green + 0.114f * blue) < 0.5f

/** 뜻에 해당하는 색 한 벌. 어두운 화면에서는 같은 뜻을 밝은 쪽 값으로 바꾼다. */
@Composable
fun toneSet(meaning: Meaning): ToneSet {
    val dark = MaterialTheme.colorScheme.background.isDarkGround()
    return when (meaning) {
        Meaning.Danger ->
            if (dark) ToneSet(Color(0xFFF2909B), Color(0x33BD2033), Tone.Red)
            else ToneSet(Tone.RedDeep, Tone.RedWash, Tone.Red)
        Meaning.Good ->
            if (dark) ToneSet(Color(0xFFA7D96C), Color(0x2E7CBE38), Tone.Green)
            else ToneSet(Tone.GreenDeep, Tone.GreenWash, Tone.Green)
        Meaning.Caution ->
            if (dark) ToneSet(Color(0xFFE3B872), Color(0x2EA96A12), Tone.Amber)
            else ToneSet(Tone.Amber, Tone.AmberWash, Tone.Amber)
        Meaning.Action ->
            if (dark) ToneSet(Tone.Blue, Color(0x2E45A1E4), Tone.Blue)
            else ToneSet(Tone.BlueDeep, Tone.BlueWash, Tone.Blue)
        Meaning.Neutral -> ToneSet(
            MaterialTheme.colorScheme.onSurfaceVariant,
            MaterialTheme.colorScheme.surfaceVariant,
            MaterialTheme.colorScheme.outlineVariant,
        )
    }
}

/**
 * 화면 맨 위의 흑연 띠.
 *
 * 화면마다 여기가 어디고 지금 무엇을 보고 있는지를 같은 자리에서 같은
 * 모양으로 말해 준다. 눈썹줄은 화면 이름, 큰 줄은 지금 상태다.
 */
@Composable
fun ScreenBand(
    eyebrow: String,
    title: String,
    sub: String? = null,
    trailing: @Composable RowScope.() -> Unit = {},
) {
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(Dim.BandRadius),
        color = Graphite.G900,
    ) {
        Box(
            Modifier.background(
                // 금속을 흉내내는 게 아니라, 위쪽이 조금 밝아야 면이 떠 보인다.
                Brush.verticalGradient(listOf(Graphite.G700, Graphite.G900))
            )
        ) {
            Row(
                Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 11.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                Column(Modifier.weight(1f)) {
                    Text(
                        eyebrow,
                        style = MaterialTheme.typography.labelSmall,
                        color = Graphite.OnDarkMuted,
                        letterSpacing = 1.8.sp,
                    )
                    Spacer(Modifier.height(2.dp))
                    Text(
                        title,
                        style = MaterialTheme.typography.titleLarge,
                        color = Graphite.OnDark,
                    )
                    if (!sub.isNullOrBlank()) {
                        Spacer(Modifier.height(2.dp))
                        Text(
                            sub,
                            style = MaterialTheme.typography.bodySmall,
                            color = Graphite.OnDarkMuted,
                        )
                    }
                }
                trailing()
            }
        }
    }
}

/**
 * 종이 한 장.
 *
 * [accent] 를 주면 왼쪽에 뜻 있는 색 띠가 선다. 목록에서 위험한 물건을
 * 스크롤만 해도 골라낼 수 있게 하는 것이 이 띠의 전부다.
 */
@Composable
fun HomeCard(
    modifier: Modifier = Modifier,
    accent: Meaning? = null,
    content: @Composable ColumnScope.() -> Unit,
) {
    val bar = accent?.let { toneSet(it).bar }
    Surface(
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(Dim.CardRadius),
        color = MaterialTheme.colorScheme.surface,
        border = BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant),
        tonalElevation = 0.dp,
        shadowElevation = 1.dp,
    ) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.Top) {
            if (bar != null) {
                Box(
                    Modifier
                        .width(Dim.AccentBar)
                        .heightIn(min = 44.dp)
                        .background(bar)
                )
            }
            Column(Modifier.weight(1f).padding(Dim.CardPad), content = content)
        }
    }
}

/**
 * 뜻 있는 한 줄.
 *
 * 경고를 회색 본문으로 줄줄이 쌓으면 여섯 줄째부터는 아무도 안 읽는다.
 * 바탕을 옅게 깔고 왼쪽에 색 띠를 세워 한 덩어리로 보이게 한다.
 */
@Composable
fun NoteRow(
    meaning: Meaning,
    text: String,
    lead: String? = null,
    modifier: Modifier = Modifier,
) {
    val t = toneSet(meaning)
    Row(
        modifier
            .fillMaxWidth()
            .background(t.wash, RoundedCornerShape(9.dp)),
        verticalAlignment = Alignment.Top,
    ) {
        Box(
            Modifier
                .width(3.dp)
                .heightIn(min = 30.dp)
                .background(t.bar, RoundedCornerShape(topStart = 9.dp, bottomStart = 9.dp))
        )
        Column(Modifier.weight(1f).padding(horizontal = 9.dp, vertical = 7.dp)) {
            if (!lead.isNullOrBlank()) {
                Text(lead, style = MaterialTheme.typography.labelMedium, color = t.fg)
                Spacer(Modifier.height(1.dp))
            }
            Text(
                text,
                style = MaterialTheme.typography.bodySmall,
                color = if (meaning == Meaning.Neutral)
                    MaterialTheme.colorScheme.onSurfaceVariant else t.fg,
            )
        }
    }
}

/** 숫자 한 칸. 라벨은 작게, 값은 크게. 대비는 숫자에 준다. */
@Composable
fun StatTile(
    label: String,
    value: String,
    modifier: Modifier = Modifier,
    meaning: Meaning = Meaning.Neutral,
    note: String? = null,
) {
    val t = toneSet(meaning)
    Column(
        modifier
            .background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(11.dp))
            .padding(horizontal = 10.dp, vertical = 9.dp),
    ) {
        Text(
            value,
            style = MaterialTheme.typography.titleLarge,
            color = if (meaning == Meaning.Neutral) MaterialTheme.colorScheme.onSurface else t.fg,
        )
        Spacer(Modifier.height(2.dp))
        Text(
            label,
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        if (!note.isNullOrBlank()) {
            Text(note, style = MaterialTheme.typography.labelSmall, color = t.fg)
        }
    }
}

/** 물건에 붙는 표. 누르는 게 아니라 읽는 것이라 칩처럼 크게 만들지 않는다. */
@Composable
fun ToneBadge(text: String, meaning: Meaning = Meaning.Neutral) {
    val t = toneSet(meaning)
    Text(
        text,
        style = MaterialTheme.typography.labelSmall,
        color = t.fg,
        fontWeight = FontWeight.Bold,
        modifier = Modifier
            .background(t.wash, RoundedCornerShape(Dim.ChipRadius))
            .padding(horizontal = 8.dp, vertical = 3.dp),
    )
}

/** 누르는 칩. 선택 상태가 색이 아니라 채움으로 드러나야 흑백에서도 읽힌다. */
@Composable
fun SelectChip(
    selected: Boolean,
    label: String,
    enabled: Boolean = true,
    onClick: () -> Unit,
) {
    val bg = if (selected) Graphite.G800 else MaterialTheme.colorScheme.surface
    val fg = when {
        !enabled -> MaterialTheme.colorScheme.outline
        selected -> Graphite.OnDark
        else -> MaterialTheme.colorScheme.onSurfaceVariant
    }
    Surface(
        onClick = onClick,
        enabled = enabled,
        shape = RoundedCornerShape(Dim.ChipRadius),
        color = bg,
        border = BorderStroke(
            1.dp,
            if (selected) Graphite.G800 else MaterialTheme.colorScheme.outlineVariant,
        ),
        modifier = Modifier.heightIn(min = 36.dp),
    ) {
        Box(
            Modifier.padding(horizontal = 12.dp, vertical = 8.dp),
            contentAlignment = Alignment.Center,
        ) {
            Text(label, style = MaterialTheme.typography.labelMedium, color = fg)
        }
    }
}

/** 칸 안의 작은 제목. */
@Composable
fun SectionLabel(text: String, modifier: Modifier = Modifier) {
    Text(
        text,
        style = MaterialTheme.typography.labelMedium,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        letterSpacing = 0.6.sp,
        modifier = modifier,
    )
}

/** 이 화면에서 하려던 일. 화면당 하나만 둔다. */
@Composable
fun PrimaryAction(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
) {
    Button(
        onClick = onClick,
        enabled = enabled,
        modifier = modifier.heightIn(min = Dim.Tap),
        shape = RoundedCornerShape(11.dp),
        colors = ButtonDefaults.buttonColors(
            containerColor = Tone.BlueDeep,
            contentColor = Color.White,
        ),
    ) { Text(text, style = MaterialTheme.typography.labelLarge) }
}

/** 곁다리 동작. 눌러도 되지만 여기가 목적지는 아니라는 뜻이다. */
@Composable
fun GhostAction(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    small: Boolean = false,
) {
    OutlinedButton(
        onClick = onClick,
        enabled = enabled,
        modifier = modifier.heightIn(min = if (small) Dim.TapSmall else Dim.Tap),
        shape = RoundedCornerShape(11.dp),
        border = BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant),
        contentPadding = PaddingValues(
            horizontal = if (small) 10.dp else 14.dp,
            vertical = 6.dp,
        ),
    ) {
        Text(
            text,
            style = if (small) MaterialTheme.typography.labelMedium
            else MaterialTheme.typography.labelLarge,
            color = if (enabled) MaterialTheme.colorScheme.onSurface
            else MaterialTheme.colorScheme.outline,
        )
    }
}
