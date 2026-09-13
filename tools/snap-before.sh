#!/usr/bin/env bash
# 바꾸기 전 화면을 같은 자료·같은 폭으로 한 번 더 뽑는다.
#
# 새로 만든 파일(Tokens/Components)은 그대로 두고, 고친 파일만 잠깐 되돌린다.
# 되돌린 상태에서도 그 둘은 아무도 안 부르므로 컴파일에 지장이 없다.
set -eu

cd "$(dirname "$0")/.."
UI=android/app/src/main/java/com/elemensha/home
GRADLE="/c/Users/eleme/AppData/Local/Gradle/gradle-8.11.1/bin/gradle"
export JAVA_HOME="/c/Program Files/Eclipse Adoptium/jdk-17.0.20.8-hotspot"

# 지금(바꾼 뒤) 그림을 먼저 챙겨 둔다. 파일 이름이 같아서 덮어쓰기 때문이다.
rm -rf tools/shots/after && mkdir -p tools/shots/after
cp android/app/src/test/snapshots/images/* tools/shots/after/

git stash push -m "ui-after" -- \
  "$UI/MainActivity.kt" \
  "$UI/ui/ListingsScreen.kt" "$UI/ui/FiltersScreen.kt" "$UI/ui/PlanScreen.kt" \
  "$UI/ui/SettingsScreen.kt" "$UI/ui/Theme.kt" "$UI/ui/CourtEntryDialog.kt"

set +e
(cd android && "$GRADLE" :app:recordPaparazziDebug --console=plain) \
  > snap-before.log 2>&1
status=$?
set -e

rm -rf tools/shots/before && mkdir -p tools/shots/before
cp android/app/src/test/snapshots/images/* tools/shots/before/ 2>/dev/null || true

git stash pop

echo "before 빌드 종료코드=$status"
ls tools/shots/before | head -20
