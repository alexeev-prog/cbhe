Многие могли открывать HEX-редакторы для анализа файла или для обучения реверс-инжинирингу. Однажды я наткнулся на интересный [материал о подсветке байтов](https://simonomi.dev/blog/color-code-your-bytes/). Недолго думая, я решил написать статью — не просто туториал по подсветке байтов, а разбор внутреннего устройства минимального hex-редактора. Мы изучим, как байты превращаются в hex-дамп, какие подходы к подсветке существуют и почему это важно для анализа бинарных данных.

Перед началом хочу показать, что у меня получилось:

![Пример](https://habrastorage.org/webt/21/b4/4c/21b44c974ea4ca1d0a880ddc906450dc.png)

<a class="anchor" id="toc"></a>
## Содержание

- [Что мы видим, открыв HEX-редактор?](#что-мы-видим-открыв-hex-редактор)
  - [Байт, ниббл и hex-разложение](#байт-ниббл-и-hex-разложение)
  - [ASCII-колонка](#ascii-колонка)
- [Подсветка!](#подсветка)
  - [Подсветка по нибблам](#подсветка-по-нибблам)
  - [Градиентная подсветка](#градиентная-подсветка)
  - [Структурная подсветка по формату](#структурная-подсветка-по-формату)
- [Архитектура проекта](#архитектура-проекта)
  - [HexFile: работа с файлом](#hexfile-работа-с-файлом)
  - [Система цветов](#система-цветов)
  - [Конфигурация: constants.py](#конфигурация-constantspy)
  - [Клавиши и терминал: keys.py и terminal.py](#клавиши-и-терминал-keyspy-и-terminalpy)
  - [Состояние редактора: state.py](#состояние-редактора-statepy)
    - [Undo-redo](#undo-redo)
    - [Поиск](#поиск)
  - [Кейбинды: handlers.py](#кейбинды-handlerspy)
  - [Рендеринг UI](#рендеринг-ui)
  - [Интерпретация байт: interpret.py](#интерпретация-байт-interpretpy)
  - [Точка входа](#точка-входа)
- [Практика!](#практика)
- [Заключение](#заключение)

<a class="anchor" id="what-we-see"></a>
# Что мы видим, открыв HEX-редактор?

Давайте начнём с краткого экскурса, как устроен HEX-редактор. Как вы знаете, он позволяет открывать бинарные (двоичные) файлы.

Основа — это само окно редактора:

![Устройство HEX-редактора](https://habrastorage.org/webt/5d/40/9b/5d409b1ce3e5ffc22d24165f2d533531.png)

Он отображает данные в виде матрицы.

Первая часть — это адрес, offset, смещение в байтах от начала файла. Первая строчка с нуля, каждая следующая прибавляет ширину дампа — количество байт в одной строке. Байт — это два hex-числа. Десятичный адрес вроде 00000016 ничего не говорит о границах, а hex-адрес 00000010 сразу показывает, что мы пересекли границу 16 байт — аккурат строка дампа.

Вторая часть — это сами байты. Байты в основном строятся по 16 (но может быть и другое число степени двойки) в колонку. Байты группируются по четыре для читаемости.

И третья часть — ASCII-панель, те же байты, но интерпретированные как символы (диапазон ASCII от 0x20 до 0x7E, от пробела до тильды). Если символ непечатаемый — пишется обычно точка.

По факту всё это — один и тот же набор байтов в трёх разных представлениях.

Это базовое представление — база для любого редактора. Дальше, когда мы будем писать свой редактор, мы будем наращивать цвет, структуру и контекст, но схема всегда остаётся одной: адрес, hex, ASCII.

<a class="anchor" id="byte-nibble"></a>
## Байт, ниббл и hex-разложение

В нашем hex-редакторе будет подсветка байт, которую мы реализуем позже. Но сначала — матчасть.

Hex-редактор работает с тремя вещами: байты, биты и нибблы. Байт — это минимальная адресуемая единица памяти, равная 8 битам. Ниббл — это 4 бита, половина байта. Слово nibble произошло от английского nibble — «откусывать» (игра слов: byte -> bite -> nibble). Ниббл принимает значение от 0 до 16, то бишь 16 вариантов. А тут как раз 16 шестнадцатеричных цифр. В итоге один ниббл = одна hex-цифра.

То есть байт 0x7F — это две половинки: старший ниббл 7 и младший ниббл F.

Кроме того, нибблы позволяют интерпретировать значение байта в цвет, чем мы и займёмся в этой статье.

Давайте разберём на примере. Возьмём байт со значением 0xA5 и посмотрим, что внутри:

![Байт 0xA5 внутри](https://habrastorage.org/webt/3e/c1/9e/3ec19e51d989376e0930896ed052fc5c.png)

Как получить значение байта из нибблов? Легко и непринуждённо: старший ниббл умножается на 16 и складывается с младшим: `0xA * 16 + 0x5 = 10 * 16 + 5 = 165`. Или в двоичном виде: `1010 0101₂ = 165₁₀ = 0xA5`.

Процессор не оперирует нибблами напрямую, но нам, кожаным мешкам, удобно мыслить именно ими при чтении hex-дампа. Когда ты видишь в hex-панели ячейку A5, можно подсознательно разделить её на две части: «A — это старшая половина, 5 — младшая».

Теперь важное следствие для hex-редактора. Когда мы выводим байт в hex-панели, мы делаем ровно две вещи: извлекаем старший ниббл `(byte >> 4) & 0x0F`, извлекаем младший ниббл `byte & 0x0F` и превращаем каждый в символ от '0' до 'F'. Это буквально несколько битовых операций:

![Пример](https://habrastorage.org/webt/26/eb/df/26ebdf997090e3739a225fbafae14a0b.png)

> Почему мы группируем по четыре байта в hex-панели? Потому что четыре байта = 32 бита = машинное слово. Группа из четырёх байт — это восемь нибблов, восемь hex-цифр. Целое 32-битное слово выглядит как непрерывная последовательность из восьми символов вроде 0000000D.

Понимание того, что байт — это два ниббла, а ниббл — это одна hex-цифра, очень важно для всего, что будет дальше описано в этой статье. Когда мы начнём красить hex-дамп, мы сможем выбирать: раскрашивать каждую цифру отдельно (подсветка по нибблам) или байт целиком (градиенты по значению). Это два разных взгляда на одни и те же данные, и каждый даёт свою информацию.

<a class="anchor" id="ascii-column"></a>
## ASCII-колонка

ASCII-панель создана для того, чтобы мы могли понять, что байты 48 65 6C 6C 6F — это «Hello».

ASCII (American Standard Code for Information Interchange) — это 7-битная кодировка, принятая в 1963 году и доработанная в 1968. Она описывает 128 символов: 33 управляющих и 95 печатных. Несмотря на возраст, это до сих пор фундамент, на котором держатся UTF-8, JSON-строки, HTTP-заголовки, имена файлов и почти всё, что касается текста в компьютерных системах.

![](https://habrastorage.org/webt/bf/f3/60/bff360998a24cf360a3677be77399365.png)

Читаемые — это 95 символов от пробела (0x20) до тильды (0x7E): буквы латиницы в обоих регистрах, цифры, знаки пунктуации, скобки, математические символы.

Собственно, чтобы отобразить байт в ASCII-формате, хватает одной строчки кода:

```Python
ch = chr(b) if 32 <= b <= 126 else "·"
```

Давайте разберём на примере первой строчки png-файла:

```
00000000    89 50 4E 47  0D 0A 1A 0A     ·PNG····
```

Байт 0x89 → вне ASCII → `·`
Байт 0x50 → печатный, `P` → `P`
Байт 0x4E → печатный, `N` → `N`
Байт 0x47 → печатный, `G` → `G`
Байт 0x0D → CR, управляющий → `·`
Байт 0x0A → LF, управляющий → `·`

Кроме того, ASCII-колонку можно подсвечивать, как в примере из нашего hex-редактора (python, curses):

```python
ASCII_PRINTABLE_START: int = 32
ASCII_PRINTABLE_END: int = 126
PAIR_ASCII_BASE: int = 270
PAIR_HEX_BASE: int = 10

def ascii_color(bval: int) -> int:
    if ASCII_PRINTABLE_START <= bval <= ASCII_PRINTABLE_END:
        return curses.color_pair(PAIR_ASCII_BASE + (bval - ASCII_PRINTABLE_START))
    return curses.color_pair(PAIR_HEX_BASE + bval)
```

Печатные символы (0x20–0x7E) получают собственную шкалу серого: 95 оттенков от тёмно-серого для малых кодов до почти белого для больших. Непечатные и вне-ASCII байты наследуют градиент из hex-панели, который мы разберём позже.

Также стоит учесть, что хоть UTF-8 обратно совместим с ASCII (байты 0x00–0x7F означают ровно то же самое), многобайтовые символы (кириллица, иероглифы) кодируются последовательностями байтов со значениями 0x80 и выше. То есть русский текст будет россыпью точек.

<a class="anchor" id="highlighting"></a>
# Подсветка!

Прочитав статью [«Your hex editor should color-code bytes»](https://simonomi.dev/blog/color-code-your-bytes/), я как раз и пришёл к идее сделать эту статью по разработке hex-редактора с фишкой в виде подсветки.

Здесь я хочу рассмотреть три уровня подсветки: базовая подсветка по нибблам, градиентная подсветка по значению байта и как фича — структурная подсветка по формату.

Исходный код проекта доступен в [моём репозитории](https://github.com/alexeev-prog/cbhe).

<a class="anchor" id="nibble-highlight"></a>
## Подсветка по нибблам

Идея в том, что каждой hex-цифре назначается цвет, зависящий от значения её старшего полубайта. Поскольку ниббл принимает 16 значений, получается 16 фиксированных цветов.

В кодовой базе это представлено в файле simple_colored.py:

```python
def color_for_high_nibble(byte_value: int) -> str:
    high_nibble = (byte_value >> 4) & 0x0F

    if byte_value == 0x00:
        return "\033[90m"
    if byte_value == 0xFF:
        return "\033[97m"

    colors = [              # Цвета (вы можете взять другие):
        "\033[91m",         # Ярко-красный
        "\033[38;5;208m",   # Оранжевый (256 цветов)
        "\033[93m",         # Ярко-жёлтый
        "\033[92m",         # Ярко-зелёный
        "\033[38;5;82m",    # Яркий желтовато-зелёный (256 цветов)
        "\033[96m",         # Ярко-голубой (циан)
        "\033[94m",         # Ярко-синий
        "\033[95m",         # Ярко-пурпурный (маджента)
        "\033[38;5;205m",   # Розово-пурпурный (256 цветов)
        "\033[38;5;50m",    # Светлый зелёно-голубой (256 цветов)
        "\033[38;5;39m",    # Яркий синий (256 цветов)
        "\033[95m",         # Повтор — ярко-пурпурный
        "\033[35m",         # Пурпурный (неяркий)
        "\033[91m",         # Повтор — ярко-красный
        "\033[90m",         # Тёмно-серый / ярко-чёрный
        "\033[91m",         # Ещё раз ярко-красный
    ]

    return colors[high_nibble]
```

Цвет привязан к старшему нибблу байта: байты 0x00–0x0F получают один цвет пары цифр, 0x10–0x1F — другой и так далее. Нуль и 0xFF обрабатываются отдельно.

Этот алгоритм подсветки даёт то, что видны повторяющиеся паттерны. Два одинаковых байта дают одинаковую цветовую пару из двух hex-цифр.

![Пример подсветки по нибблам](https://habrastorage.org/webt/b7/7d/20/b77d20d5ffa603c522dc82e7bc65821b.png)

Собственно, есть ограничение: классификация идёт по нибблу, а не по смыслу. Байты 0x00 (NUL) и 0x20 (SPACE) получат разные цвета, хотя оба относятся к управляющим/разделительным символам. Цвет отвечает на вопрос «чему равен старший полубайт?», а не «что это за байт?».

<a class="anchor" id="gradient-highlight"></a>
## Градиентная подсветка

В отличие от дискретной раскраски по нибблам, здесь цвет непрерывно зависит от значения байта. В текущем проекте это реализовано в примере gradient_colored.py:

```python
COLOR_RESET = "\033[0m"


def hsv_to_rgb(h: float, s: float, v: float) -> tuple[int, int, int]:
    h = h % 360.0
    c = v * s
    x = c * (1.0 - abs((h / 60.0) % 2.0 - 1.0))
    m = v - c

    if 0 <= h < 60:
        r, g, b = c, x, 0.0
    elif 60 <= h < 120:
        r, g, b = x, c, 0.0
    elif 120 <= h < 180:
        r, g, b = 0.0, c, x
    elif 180 <= h < 240:
        r, g, b = 0.0, x, c
    elif 240 <= h < 300:
        r, g, b = x, 0.0, c
    else:
        r, g, b = c, 0.0, x

    return int((r + m) * 255), int((g + m) * 255), int((b + m) * 255)


def gradient_color(byte_value: int) -> str:
    if byte_value == 0x00:
        return "\033[38;2;64;64;64m"

    if byte_value == 0xFF:
        return "\033[38;2;255;255;255m"

    hue = (byte_value / 255.0) * 360.0

    r, g, b = hsv_to_rgb(hue, 0.8, 0.9)

    return f"\033[38;2;{r};{g};{b}m"
```

Отображение значения байта (0–255) на цветовой круг HSV даёт непрерывный спектр: hue пробегает от 0° до 360° пропорционально значению. Насыщенность 0.8 и яркость 0.9 были выбраны экспериментально мной, чтобы цвета были комфортными.

Получается тепловая карта, где резкие границы между разными цветами подсказывают, где в файле меняется характер данных.

![Пример градиентной подсветки](https://habrastorage.org/webt/3b/c4/1f/3bc41f0b9f216fbf0954b9b0d9dd8800.png)

В основном редакторе градиентная подсветка реализована в colors.py. Функция _byte_to_rgb делает ровно то же, что и gradient_color в примере, но возвращает RGB-компоненты для curses вместо ANSI-escape-последовательности, ибо наш основной редактор написан на curses. Curses — библиотека для TUI, которая для подсветки использует встроенный функционал цветовых пар.

```python
def _byte_to_rgb(bval: int) -> tuple[int, int, int]:
    if bval == BYTE_MIN:
        return DEFAULT_BYTE_RGB
    if bval == BYTE_MAX:
        return MAX_BYTE_RGB

    hue = (bval / 255.0) * 360.0
    return _hsv_to_rgb(hue, 0.8, 0.9)
```

При инициализации для каждого из 256 возможных значений байта создаётся отдельная цветовая пара, но если терминал не поддерживает изменение палитры, то все байты получают белый цвет.

Градиентная подсветка уже может ответить на вопрос «какое значение у байта?». В отличие от ниббл-подхода, здесь цвет несёт информацию о величине: два соседних значения 0x7F и 0x80 будут почти одного оттенка, а 0x00 и 0xFF — на противоположных концах спектра.

<a class="anchor" id="structural-highlight"></a>
## Структурная подсветка по формату

Градиенты — это, безусловно, делают пользовательский опыт более дружелюбным. Но мне не давала покоя мысль, что можно подсвечивать отдельно сигнатуры форматов файла!

Градиенты хороши для общего обзора, но не отвечают на вопрос «что значит этот байт?». PNG-сигнатура \x89PNG и поле ширины изображения — оба получат просто цвет по значению. Чтобы редактор понимал контекст, добавлен третий слой: структурная подсветка по формату файла.

![Пример сигнатуры](https://habrastorage.org/webt/55/eb/45/55eb459e24a48fe4bf298475ff56d68d.png)

При открытии файла наш редактор читает первые 1024 байта и прогоняет их через функцию детектинга формата. Тот, в свою очередь, перебирает все зарегистрированные форматы и проверяет по списку сигнатур. Если всё совпадает — формат определён.

В проекте четыре встроенных формата. PNG ищет `\x89PNG\r\n\x1a\n` на смещении 0. ELF — `\x7fELF`. JPEG — `\xff\xd8\xff`. ZIP — `PK\x03\x04`. Каждый описан как `FormatDef` — датакласс с именем, MIME-типом, списком сигнатур и списком полей.

```python
@dataclass
class FormatDef:
    name: str
    mime: str
    signatures: list[tuple[int, bytes]]
    fields: list[FieldDef]
    _index: dict[int, FieldDef] = field(default_factory=dict, init=False, repr=False)
```

И вот сам список встроенных форматов. Каюсь, для облегчения навайбкодил этот момент, так как это рутинная и муторная работа:

```python
class FieldType(Enum): # Тип поля
    MAGIC = auto()
    SIZE = auto()
    OFFSET = auto()
    FLAGS = auto()
    CHECKSUM = auto()
    VERSION = auto()
    DATA = auto()
    RESERVED = auto()
    HEADER = auto()
    UNKNOWN = auto()


@dataclass
class FieldDef: # Дефиниция поля
    offset: int
    length: int
    name: str
    ftype: FieldType


BUILTIN_FORMATS: list[FormatDef] = [
    FormatDef(
        name="PNG",
        mime="image/png",
        signatures=[(0, b"\x89PNG\r\n\x1a\n")],
        fields=[
            FieldDef(0, 8, "Signature", FieldType.MAGIC),
            FieldDef(8, 4, "IHDR Length", FieldType.SIZE),
            FieldDef(12, 4, "IHDR Chunk Type", FieldType.HEADER),
            FieldDef(16, 4, "Width", FieldType.SIZE),
            FieldDef(20, 4, "Height", FieldType.SIZE),
            FieldDef(24, 1, "Bit Depth", FieldType.FLAGS),
            FieldDef(25, 1, "Color Type", FieldType.FLAGS),
            FieldDef(26, 1, "Compression", FieldType.FLAGS),
            FieldDef(27, 1, "Filter", FieldType.FLAGS),
            FieldDef(28, 1, "Interlace", FieldType.FLAGS),
            FieldDef(29, 4, "CRC", FieldType.CHECKSUM),
        ],
    ),
    FormatDef(
        name="ELF",
        mime="application/x-elf",
        signatures=[(0, b"\x7fELF")],
        fields=[
            FieldDef(0, 4, "Magic", FieldType.MAGIC),
            FieldDef(4, 1, "Class", FieldType.VERSION),
            FieldDef(5, 1, "Endianness", FieldType.FLAGS),
            FieldDef(6, 1, "Version", FieldType.VERSION),
            FieldDef(7, 1, "OS/ABI", FieldType.FLAGS),
            FieldDef(8, 1, "ABI Version", FieldType.VERSION),
            FieldDef(9, 7, "Padding", FieldType.RESERVED),
            FieldDef(16, 2, "Type", FieldType.FLAGS),
            FieldDef(18, 2, "Machine", FieldType.FLAGS),
            FieldDef(20, 4, "ELF Version", FieldType.VERSION),
            FieldDef(24, 4, "Entry Point (32-bit)", FieldType.OFFSET),
            FieldDef(28, 4, "PH Offset (32-bit)", FieldType.OFFSET),
            FieldDef(32, 4, "SH Offset (32-bit)", FieldType.OFFSET),
            FieldDef(36, 4, "Flags", FieldType.FLAGS),
            FieldDef(40, 2, "Header Size", FieldType.SIZE),
            FieldDef(42, 2, "PH Entry Size", FieldType.SIZE),
            FieldDef(44, 2, "PH Count", FieldType.SIZE),
            FieldDef(46, 2, "SH Entry Size", FieldType.SIZE),
            FieldDef(48, 2, "SH Count", FieldType.SIZE),
            FieldDef(50, 2, "SH String Index", FieldType.OFFSET),
        ],
    ),
    FormatDef(
        name="JPEG",
        mime="image/jpeg",
        signatures=[(0, b"\xff\xd8\xff")],
        fields=[
            FieldDef(0, 2, "SOI Marker", FieldType.MAGIC),
            FieldDef(2, 1, "APP0 Marker", FieldType.MAGIC),
            FieldDef(3, 1, "APP0 Marker", FieldType.MAGIC),
            FieldDef(4, 2, "APP0 Length", FieldType.SIZE),
            FieldDef(6, 5, "JFIF Identifier", FieldType.HEADER),
            FieldDef(11, 2, "JFIF Version", FieldType.VERSION),
            FieldDef(13, 1, "Density Units", FieldType.FLAGS),
            FieldDef(14, 2, "X Density", FieldType.SIZE),
            FieldDef(16, 2, "Y Density", FieldType.SIZE),
            FieldDef(18, 1, "Thumbnail Width", FieldType.SIZE),
            FieldDef(19, 1, "Thumbnail Height", FieldType.SIZE),
        ],
    ),
    FormatDef(
        name="ZIP",
        mime="application/zip",
        signatures=[(0, b"PK\x03\x04")],
        fields=[
            FieldDef(0, 4, "Local File Signature", FieldType.MAGIC),
            FieldDef(4, 2, "Version Needed", FieldType.VERSION),
            FieldDef(6, 2, "Flags", FieldType.FLAGS),
            FieldDef(8, 2, "Compression Method", FieldType.FLAGS),
            FieldDef(10, 2, "Last Mod Time", FieldType.DATA),
            FieldDef(12, 2, "Last Mod Date", FieldType.DATA),
            FieldDef(14, 4, "CRC-32", FieldType.CHECKSUM),
            FieldDef(18, 4, "Compressed Size", FieldType.SIZE),
            FieldDef(22, 4, "Uncompressed Size", FieldType.SIZE),
            FieldDef(26, 2, "Filename Length", FieldType.SIZE),
            FieldDef(28, 2, "Extra Field Length", FieldType.SIZE),
        ],
    ),
]
```

Каждое поле в формате имеет тип из перечисления `FieldType` и человекопонятное имя. Тип определяет цвет в hex-панели и ASCII-колонке:

| Тип поля | Цвет | Назначение |
|---|---|---|
| MAGIC | жёлтый | сигнатуры и магические числа |
| SIZE | зелёный | размеры блоков, полей, файлов |
| OFFSET | голубой | указатели, смещения |
| CHECKSUM | красный | контрольные суммы, CRC |
| VERSION | синий | версии формата |
| FLAGS | пурпурный | битовые флаги, перечисления |
| HEADER | чёрный на жёлтом фоне | заголовки секций |
| RESERVED | белый на белом (инвертированный) | зарезервированные поля |
| DATA | белый | область данных, полезная нагрузка |
| UNKNOWN | белый | тип не указан или неизвестен |

Цветовые пары для типов полей инициализируются в `_init_field_pairs()` стандартными цветами curses. Это отдельные пары, не пересекающиеся с градиентными слотами.

```python
def _init_field_pairs() -> None:
    field_colors = [
        (PAIR_FIELD_MAGIC, curses.COLOR_YELLOW, -1),
        (PAIR_FIELD_SIZE, curses.COLOR_GREEN, -1),
        (PAIR_FIELD_OFFSET, curses.COLOR_CYAN, -1),
        (PAIR_FIELD_FLAGS, curses.COLOR_MAGENTA, -1),
        (PAIR_FIELD_CHECKSUM, curses.COLOR_RED, -1),
        (PAIR_FIELD_VERSION, curses.COLOR_BLUE, -1),
        (PAIR_FIELD_DATA, curses.COLOR_WHITE, -1),
        (PAIR_FIELD_RESERVED, -1, curses.COLOR_WHITE),
        (PAIR_FIELD_HEADER, curses.COLOR_BLACK, curses.COLOR_YELLOW),
        (PAIR_FIELD_UNKNOWN, curses.COLOR_WHITE, -1),
    ]
    for pair_id, fg, bg in field_colors:
        curses.init_pair(pair_id, fg, bg)
```

Как видно по коду, я старался придерживаться открытости и расширяемости. Встроенные форматы хранятся в списке BUILTIN_FORMATS и регистрируются при запуске. Если вы хотите добавить свой формат, то сделать это просто — через новый FormatDef прямо в коде либо через JSON-файл. Благодаря тому что формат полей уже задан, это было легко реализовать.

Вот пример пользовательского формата:

```json
    {
        "name": "GIF",
        "mime": "image/gif",
        "signatures": [
            {"offset": 0, "hex": "47494638"}
        ],
        "fields": [
            {"offset": 0, "length": 3, "name": "Signature", "type": "MAGIC"},
            {"offset": 3, "length": 3, "name": "Version", "type": "VERSION"},
            {"offset": 6, "length": 2, "name": "Screen Width", "type": "SIZE"},
            {"offset": 8, "length": 2, "name": "Screen Height", "type": "SIZE"},
            {"offset": 10, "length": 1, "name": "Flags", "type": "FLAGS"},
            {"offset": 11, "length": 1, "name": "Background Color Index", "type": "DATA"},
            {"offset": 12, "length": 1, "name": "Pixel Aspect Ratio", "type": "FLAGS"},
            {"offset": 13, "length": 3, "name": "Image Descriptor", "type": "HEADER"},
            {"offset": 16, "length": 2, "name": "Image Left Position", "type": "OFFSET"},
            {"offset": 18, "length": 2, "name": "Image Top Position", "type": "OFFSET"},
            {"offset": 20, "length": 2, "name": "Image Width", "type": "SIZE"},
            {"offset": 22, "length": 2, "name": "Image Height", "type": "SIZE"},
            {"offset": 24, "length": 1, "name": "Image Flags", "type": "FLAGS"},
            {"offset": 25, "length": 1, "name": "LZW Minimum Code Size", "type": "FLAGS"},
            {"offset": 26, "length": 1, "name": "Trailer", "type": "CHECKSUM"}
        ]
    },
```

Новые форматы добавляются в глобальный список `FORMATS`, по которому `detect_format` итерируется при открытии файла. Порядок регистрации имеет значение — победит последний зарегистрированный формат, а встроенные форматы загружаются перед кастомными, так что пользователь может переопределить встроенный, зарегистрировав свой формат с тем же именем после загрузки JSON.

Вообще, сигнатуры — это крайне интересная вещь, которую надо изучить, если вы хотите пойти в реверс-инжиниринг. А hex-редактор с подсветкой формата поможет в этом.

Все эти три уровня подсветки улучшают UX в самом прямом смысле. Даже мне самому легче пользоваться с подсветкой, она помогает не тонуть в массиве байтов.

<a class="anchor" id="architecture"></a>
# Архитектура проекта

Ну что, время перейти к самому сладкому — самому коду и созданию hex-редактора! Писать мы будем на чистом Python 3.14 и встроенной библиотекой curses. Господам из Windows придётся немного пострадать: curses не входит в стандартную поставку для Windows, и вам придётся установить `windows-curses`. Но даже так возможны нюансы работы — в первую очередь из-за цветов. Так что работоспособность на Windows не гарантируется, можете работать через WSL.

Проект простой, так что я не стал разбивать на множество слоёв и абстракций и обошёлся в 10 файлов:

```
src/cbhe/
├── __init__.py     # Точка входа, главный цикл, аргументы командной строки
├── constants.py    # Конфигурация: номера цветовых пар, раскладки клавиш, ширины дампа
├── keys.py         # Коды клавиш (обёртка над curses.KEY_*)
├── terminal.py     # Обёртка над curses: setup, read_key, screen_size
├── hexfile.py      # Чтение, кеширование, запись, поиск по файлу
├── state.py        # Состояние редактора: режим, курсор, undo/redo, поиск
├── handlers.py     # Обработка клавиш для каждого режима
├── ui.py           # Отрисовка: строки дампа, заголовок, статус, панель интерпретации
├── colors.py       # Инициализация 350+ цветовых пар, функции выбора цвета байта
├── formats.py      # Описания форматов, детектирование сигнатур, загрузка из JSON
└── interpret.py    # Интерпретация байта как чисел и строк
```

Я старался следовать фундаментальным принципам: DRY, KISS и, самое главное, SRP из SOLID (принцип единой ответственности). Модуль hexfile не знает про curses, модуль ui не читает клавиши. Это позволит сменить библиотеку отрисовки на другую, не переписывая несколько файлов, а логика данных и состояние останутся нетронутыми.

Почему я выбрал curses? Всё просто — предельная простота. Textual даёт красивую разметку, но тащит за собой Rich и много бойлерплейта для такого небольшого проекта. Curses нативно оперирует цветовыми парами, которых у нас 256 только на градиент. И главное — curses не требует установки ничего, кроме стандартной библиотеки Python.

Кроме того, я учёл, что терминал может не поддерживать изменение цветов, так что если поддержки нет — цветового оформления в виде градиента не будет.

Этот же принцип применён к панели интерпретации: она рисуется только если хватает ширины терминала. Если окно слишком узкое — панель просто не показывается, не ломая вёрстку.

![Скриншот интерфейса](https://habrastorage.org/webt/1d/ac/03/1dac03b20d48ee9864aa55f7baeaa3cd.png)

Давайте перейдём к тому, как я планировал UI/UX редактора. Я решил немного вдохновиться режимами из VIM’а, переделав их под себя. Есть три режима:

1. Стандартный READ (`r`). Чтение без редактирования, поиск и скроллинг.
2. HEX (`h`) — режим hex-панели. Позволяет уже не только скроллить, но и двигать курсор по байтам. Кейбинд `e` входит в редактирование, можно менять байты по нибблам.
3. ASCII (`a`) — курсор в ASCII-панели. По кейбинду `e` также режим редактирования, ввод символов напрямую меняет байты.

При редактировании изменённые байты подсвечиваются красным фоном (dirty) до сохранения. Работает undo/redo: `u` отменяет последнее изменение, `Ctrl+R` — возвращает. История — 1000 записей, две раздельные стопки. Сохранение по `Ctrl+S` сбрасывает dirty-состояние и историю.

Поиск есть двух видов: `/` — ASCII-поиск (поиск по строке), `?` — hex-поиск (вводишь `ff d8 ff` или `FFD8FF`). Найденные совпадения подсвечиваются жёлтым фоном. `n` — следующее совпадение, `N` — предыдущее. Поиск кольцевой: дойдя до конца файла, переходит в начало.

Клавиша `i` включает панель интерпретации справа. Для байта под курсором показывает: int8/uint8, int16/32/64 в LE и BE, float32/64, битовое представление, UTF-8 из 4 и 8 байт. Панель автоматически скрывается, если не хватает ширины терминала.

Клавиша `w` переключает ширину дампа: 8, 16 или 32 байта в строке. `g` — переход по адресу.

Строка заголовка показывает: режим, имя файла, размер, ширину дампа, распознанный формат, процент просмотра. Строка статуса под дампом показывает offset в hex и dec, значение байта в hex/dec/char, имя и тип поля формата, если байт принадлежит известному полю. В правой части статусной строки — сообщения: результат поиска, undo/redo, ошибки.

Точкой входа является файл `__init__.py`. Он разбирает аргументы командной строки, загружает форматы, инициализирует цвета, создаёт объекты. Цикл на каждой итерации отрисовывает весь фрейм, читает клавишу и передаёт её. Простой синхронный цикл, обновляющий состояние целиком.

Кстати, насчёт аргументов командной строки: я оформил их ниже в виде таблицы:

| Флаг | Описание |
|---|---|
| `-f`, `--formats` | JSON-файл с пользовательскими форматами (можно несколько) |
| `-w`, `--width` | Начальная ширина дампа: 8, 16 или 32 (по умолчанию 16) |
| `-m`, `--mode` | Начальный режим: read, hex или ascii (по умолчанию read) |
| `--no-auto-detect` | Отключить автоопределение формата |
| `--format-dir` | Загрузить все *.json из указанной директории как форматы |

В первую очередь я создал их поддержку из-за того, что захотел поддерживать кастомные пользовательские форматы файлов для подсветки. Также по традиции использовал стандартный модуль argparse, хотя думал сначала установить click, но раз проект без внешних зависимостей, а логика не сложная, можно обойтись и стандартным argparse.

<a class="anchor" id="hexfile"></a>
## HexFile: работа с файлом

Редактор не должен загружать сразу весь файл.

Можно, конечно, обойтись следующей конструкцией:

```python
with open(filename, 'rb') as f:
    data = f.read()

# или

with open('file.bin', 'rb') as f:
    data = bytearray(f.read())
```

Но в случае TUI это плохо, так как могут возникнуть проблемы с рендерингом. Вместо прямого полного чтения стоит использовать технику ленивой загрузки чанками. HexFile как раз этим и занимается: он хранит LRU (Least Recent Usage) кеш строк, реализованный через OrderedDict:

```python
class _LRURowCache:
    def __init__(self, capacity: int) -> None:
        self._cap = capacity
        self._store: OrderedDict[int, bytearray] = OrderedDict()

    def get(self, key: int) -> Optional[bytearray]:
        if key not in self._store:
            return None
        self._store.move_to_end(key)
        return self._store[key]

    def put(self, key: int, value: bytearray) -> None:
        if key in self._store:
            self._store.move_to_end(key)
        self._store[key] = value
        if len(self._store) > self._cap:
            self._store.popitem(last=False)

    def update(self, key: int, col: int, value: int) -> None:
        row = self._store.get(key)
        if row is not None and col < len(row):
            row[col] = value

    def clear(self) -> None:
        self._store.clear()

    def __contains__(self, key: int) -> bool:
        return key in self._store
```

> OrderedDict взят из-за того, что он сохраняет порядок включения элементов. Да, с Python 3.7 стандартный dict уже сохраняет порядок, но использование OrderedDict выражает намерение именно в упорядоченности, а также позволяет использовать метод `move_to_end`, что требует меньше кода, чем стандартный dict.

Когда кеш переполняется, самый старый элемент удаляется. Ёмкость — 8192 строки. При ширине дампа 16 байт это 128 КБ данных, что умещается даже в кеш процессора.

Метод update позволяет модифицировать закешированную строку на месте, не вынимая её из кеша. Это нужно для dirty-механики: когда пользователь меняет байт, мы сразу обновляем и кеш, и словарь «грязных» смещений.

Если запрошенной строки нет в кеше, существует функция `_load_region`:

```python
def _load_region(self, anchor_row: int) -> None:
    row_start = max(0, anchor_row - self.PREFETCH_ROWS // 4)
    byte_start = row_start * self.width
    byte_len = min(self.PREFETCH_ROWS * self.width, self.size - byte_start)

    if byte_len <= 0:
        return

    raw = self._read_raw(byte_start, byte_len)

    for i in range(0, len(raw), self.width):
        r = row_start + i // self.width
        self._cache.put(r, bytearray(raw[i : i + self.width]))
```

Эта функция читает с диска блок в 512 строк (prefetch) с якорем на четверть выше запрошенной строки. Так при скроллинге вперёд данные уже подгружены.

Для файлов больше 64 МБ обычное чтение через open().read() создаёт лишнее копирование данных из буфера ядра в userspace. Здесь нам поможет mmap — сисколл, который позволяет отобразить содержимое файла или устройства в адресное пространство процесса.

mmap отображает файл в виртуальную память процесса, и операционная система сама решает, какие страницы держать в физической памяти. Это даёт два преимущества: экономия памяти и нативный поиск через self._mmap.find() без ручного чанкования.

```python
    def _open_mmap(self) -> None:
        if not self._use_mmap or self.size == 0:
            return
        try:
            self._mmap_fh = open(self.path, "rb")  # type: ignore
            self._mmap = mmap.mmap(self._mmap_fh.fileno(), 0, access=mmap.ACCESS_READ)  # type: ignore
        except (OSError, ValueError):
            self._mmap = None
            if self._mmap_fh:
                self._mmap_fh.close()
                self._mmap_fh = None

    def _close_mmap(self) -> None:
        if self._mmap is not None:
            try:
                self._mmap.close()
            except Exception:
                pass
            self._mmap = None
        if self._mmap_fh is not None:
            try:
                self._mmap_fh.close()
            except Exception:
                pass
            self._mmap_fh = None
```

При сохранении mmap закрывается, данные пишутся через обычный файловый дескриптор, затем mmap открывается заново.

Но, прошу заметить, мы не пишем изменения сразу в файл. Вместо этого они накапливаются в словаре, где ключ — абсолютное смещение, а значение — новый байт. При отрисовке get_row накладывает грязные байты поверх данных из кеша:

```python
    def get_row(self, row: int) -> Optional[bytearray]:
        if not (0 <= row < self.total_rows):
            return None

        cached = self._cache.get(row)
        if cached is None:
            self._load_region(row)
            cached = self._cache.get(row)

        if cached is None:
            return None

        data = bytearray(cached)
        start_offset = row * self.width
        for col in range(len(data)):
            off = start_offset + col
            if off in self._dirty:
                data[col] = self._dirty[off]

        return data
```

При сохранении dirty-смещения группируются в последовательные блоки и пишутся одним вызовом fh.write(block). Это быстрее, чем seek + write для каждого байта.

```python
def save(self) -> None:
    if not self._dirty:
        return

    groups = _group_consecutive(list(self._dirty.items()))

    self._close_mmap()

    with open(self.path, "r+b") as fh:
        for offset, block in groups:
            fh.seek(offset)
            fh.write(block)

    self._dirty.clear()
    self._cache.clear()
    self._use_mmap = self.size >= _LARGE_FILE_THRESHOLD
    self._open_mmap()
    self.file_format = None
    self._detect_format()
```

Ну и также затронем определение формата. При открытии файла читаются первые 1024 байта и передаются в функцию detect_format из formats.py. Результат сохраняется в self.file_format и используется при отрисовке для структурной подсветки, но если формат не определён — file_format остаётся None, и работает только градиентная подсветка.

```python
def _detect_format(self) -> None:
    try:
        header = self._read_raw(0, 1024)
        self.file_format = detect_format(bytes(header))
    except (IOError, OSError):
        self.file_format = None
```

Полный исходный код доступен по [ссылке](https://github.com/alexeev-prog/cbhe/blob/main/src/cbhe/hexfile.py).

<a class="anchor" id="color-system"></a>
## Система цветов

Модуль colors.py инициализирует все требуемые цветовые пары для curses. Всего их шесть групп: базовые (адрес, курсор, dirty), градиентные (256 значений байта), типы полей (10 пар), статусная строка, панель интерпретации, поиск.

Как мы ранее говорили, я интегрировал градиентную подсветку: для каждого из 256 возможных значений байта создаётся отдельная цветовая пара. Значение байта отображается на hue от 0° до 360° через HSV, насыщенность 0.8, яркость 0.9. Нулевой байт получает тёмно-серый (64, 64, 64), 0xFF — белый (255, 255, 255).

```python
def _byte_to_rgb(bval: int) -> tuple[int, int, int]:
    if bval == BYTE_MIN:
        return DEFAULT_BYTE_RGB
    if bval == BYTE_MAX:
        return MAX_BYTE_RGB

    hue = (bval / 255.0) * 360.0
    return _hsv_to_rgb(hue, 0.8, 0.9)
```

Функция _hsv_to_rgb — стандартный алгоритм конвертации HSV в RGB, шесть секторов цветового круга:

```python
def _hsv_to_rgb(h: float, s: float, v: float) -> tuple[int, int, int]:
    h = h % 360.0
    c = v * s
    x = c * (1.0 - abs((h / 60.0) % 2.0 - 1.0))
    m = v - c

    if h < 60:        r, g, b = c, x, 0.0
    elif h < 120:     r, g, b = x, c, 0.0
    elif h < 180:     r, g, b = 0.0, c, x
    elif h < 240:     r, g, b = 0.0, x, c
    elif h < 300:     r, g, b = x, 0.0, c
    else:             r, g, b = c, 0.0, x

    return (int((r + m) * 255), int((g + m) * 255), int((b + m) * 255))
```

Инициализация проверяет, поддерживает ли терминал изменение палитры:

```python
def _init_hex_pairs() -> None:
    rich = curses.can_change_color() and curses.COLORS > 16

    for bval in range(COLOR_SLOTS):
        slot = 16 + bval
        pair_id = PAIR_HEX_BASE + bval

        if rich and _init_color_slot(slot, *_byte_to_rgb(bval)):
            curses.init_pair(pair_id, slot, -1)
        else:
            curses.init_pair(pair_id, curses.COLOR_WHITE, -1)
```

Если поддерживает — в цветовые слоты 16–271 записываются RGB-значения через init_color и создаются пары с этими слотами. Если терминал не поддерживает изменение палитры — все 256 пар получают белый цвет. Редактор работает, просто без подсветки.

Функция hex_color возвращает готовую пару:

```python
def hex_color(bval: int) -> int:
    return curses.color_pair(PAIR_HEX_BASE + bval)
```

Единственное различие между панелями — в том, что отображается: hex-цифры или символ/точка. Цветовая схема одна и та же. Символ-заполнитель · для непечатных байтов получает цвет, соответствующий значению байта по градиенту — например, нулевой байт будет тёмно-серой точкой, байт 0xFF — белой точкой.

Вообще все пары инициализируются так:

```python
def init_colors() -> None:
    curses.start_color()
    curses.use_default_colors()

    _init_base_pairs()
    _init_field_pairs()
    _init_hex_pairs()
    _init_extra_pairs()
    _init_interpret_pairs()
```

Чтобы не захламлять статью, весь код показывать не буду, он доступен по [ссылке](https://github.com/alexeev-prog/cbhe/blob/main/src/cbhe/colors.py).

<a class="anchor" id="constants"></a>
## Конфигурация: constants.py

Константы я вынес в отдельный модуль, чтобы не размазывать магические числа по остальным файлам. Здесь собрано всё, что не меняется во время работы редактора, но используется в нескольких местах одновременно.

Номера цветовых пар для curses начинаются с единицы и идут блоками. Базовые пары занимают диапазон 1–9: адрес, разделители, заголовок, подсказки, подсветка, курсор, dirty. Градиентные пары — с 10 по 265, по одной на каждое значение байта. Пары полей формата — с 366 по 375, статусная строка и поиск — 376–378, панель интерпретации — 379–381.

Словарь FIELD_TYPE_COLORS связывает строковое имя типа поля с номером цветовой пары.

```python
FIELD_TYPE_COLORS = {
    "MAGIC": PAIR_FIELD_MAGIC,
    "SIZE": PAIR_FIELD_SIZE,
    "OFFSET": PAIR_FIELD_OFFSET,
    "FLAGS": PAIR_FIELD_FLAGS,
    "CHECKSUM": PAIR_FIELD_CHECKSUM,
    "VERSION": PAIR_FIELD_VERSION,
    "DATA": PAIR_FIELD_DATA,
    "RESERVED": PAIR_FIELD_RESERVED,
    "HEADER": PAIR_FIELD_HEADER,
    "UNKNOWN": PAIR_FIELD_UNKNOWN,
}
```

Перечисление EditorMode задаёт три состояния, в которых может находиться редактор. Мы будем использовать его в следующем блоке, посвящённом как раз состоянию редактора.

```python
class EditorMode(Enum):
    READ = auto()
    HEX = auto()
    ASCII = auto()
```

И также идёт настройка кейбинд-подсказок и цветовые константы.

В принципе, не вижу смысла разбирать дотошно, весь код предельно понятен. Полный файл доступен по [ссылке](https://github.com/alexeev-prog/cbhe/blob/main/src/cbhe/constants.py).

<a class="anchor" id="keys-terminal"></a>
## Клавиши и терминал: keys.py и terminal.py

Эти два модуля — тонкая абстракция над конкретным бекендом отрисовки. Сейчас бекенд — curses, но если я захочу переписать редактор на Textual, к примеру, мне достаточно заменить только keys.py, terminal.py и ui.py.

keys.py просто реэкспортирует коды клавиш из curses и добавляет константы для тех клавиш, у которых нет именованных идентификаторов:

```python
import curses

KEY_UP = curses.KEY_UP
KEY_DOWN = curses.KEY_DOWN
KEY_LEFT = curses.KEY_LEFT
KEY_RIGHT = curses.KEY_RIGHT
KEY_HOME = curses.KEY_HOME
KEY_END = curses.KEY_END
KEY_PPAGE = curses.KEY_PPAGE
KEY_NPAGE = curses.KEY_NPAGE
KEY_BACKSPACE = curses.KEY_BACKSPACE
KEY_DC = curses.KEY_DC
KEY_RESIZE = curses.KEY_RESIZE

KEY_ESC = 27
KEY_CTRL_R = 18
KEY_CTRL_S = 19
KEY_BACKSPACE_ALT1 = 127
KEY_BACKSPACE_ALT2 = 8

GOTO_KEYS = {ord("g"), ord("G")}
SEARCH_ASCII_KEY = ord("/")
SEARCH_HEX_KEY = ord("?")
SEARCH_NEXT_KEY = ord("n")
SEARCH_PREV_KEY = ord("N")
INTERPRET_KEYS = {ord("i"), ord("I")}
QUIT_KEYS = {ord("q"), ord("Q")}
```

Три варианта Backspace нужны потому, что разные терминалы отправляют разные коды: классический Ctrl+H (8), DEL (127) и curses.KEY_BACKSPACE (обычно 263). Все три обрабатываются одинаково — удаление предыдущего байта.

terminal.py оборачивает четыре curses-функции, которые используются в главном цикле:

```python
import curses
from typing import Any, Callable

def setup(stdscr: Any) -> None:
    curses.curs_set(0)
    stdscr.keypad(True)

def run_with_wrapper(fn: Callable[..., None], *args: Any) -> None:
    curses.wrapper(fn, *args)

def read_key(stdscr: Any) -> int:
    return stdscr.getch()

def clear(stdscr: Any) -> None:
    stdscr.clear()

def screen_size(stdscr: Any) -> tuple[int, int]:
    return stdscr.getmaxyx()
```

Выделение этих двух модулей может показаться избыточным, но я специально так делал, чтобы логика не знала о curses и использовала абстракции. Переписать можно будет легко на другую библиотеку, без мучений с тем, что, к примеру, `__init__.py` импортирует curses и работает с ним, хотя он не должен. Так, кстати, было в первой версии проекта, затем я увидел этот импорт и понял, что curses не должен импортироваться в точку входа.

Исходники: [keys.py](https://github.com/alexeev-prog/cbhe/blob/main/src/cbhe/keys.py) и [terminal.py](https://github.com/alexeev-prog/cbhe/blob/main/src/cbhe/terminal.py).

<a class="anchor" id="state"></a>
## Состояние редактора: state.py

state.py — модуль, отвечающий за состояние редактора. Он не читает файлы, не рендерит интерфейс, он является узлом, хранящим и реализующим логику. По сути это датакласс, мутирующий в ответ на действия пользователя.

```python
@dataclass
class _UndoEntry:
    row: int
    col: int
    old_val: int
    new_val: int


@dataclass
class SearchState:
    query: bytes = b""
    last_offset: int = -1
    match_len: int = 0
    is_hex: bool = False


@dataclass
class StatusMessage:
    text: str = ""
    is_error: bool = False


@dataclass
class EditorState:
    hf: HexFile
    top_row: int = 0
    mode: EditorMode = EditorMode.READ
    editing: bool = False
    cur_row: int = 0
    cur_col: int = 0
    hex_nibble: int = 0
    show_interpret: bool = False
    search: SearchState = field(default_factory=SearchState)
    status: StatusMessage = field(default_factory=StatusMessage)
    _undo_stack: deque[_UndoEntry] = field(
        default_factory=lambda: deque(maxlen=UNDO_LIMIT), init=False, repr=False
    )
    _redo_stack: deque[_UndoEntry] = field(
        default_factory=lambda: deque(maxlen=UNDO_LIMIT), init=False, repr=False
    )
```

Поле hf — экземпляр HexFile, через который идут все операции с данными. top_row — первая видимая строка дампа, от неё считается скроллинг. mode и editing определяют текущий режим: READ, HEX, ASCII, и внутри HEX/ASCII — находимся ли мы в режиме редактирования.

Свойство cursor возвращает координаты курсора только если режим не READ — в READ курсора нет, пользователь просто скроллит файл:

```python
@property
def cursor(self) -> Optional[tuple[int, int]]:
    return (self.cur_row, self.cur_col) if self.mode != EditorMode.READ else None
```

Навигация курсора реализована в move_cursor. При выходе за левую границу строки курсор перескакивает на последний байт предыдущей строки, при выходе за правую — на первый байт следующей. Границы файла проверяются через total_rows и _max_col:

```python
def move_cursor(self, dr: int, dc: int) -> None:
    col = self.cur_col + dc
    row = self.cur_row + dr
    w = self.hf.width

    if col < 0:
        col, row = w - 1, row - 1
    elif col >= w:
        col, row = 0, row + 1

    row = max(0, min(row, self.hf.total_rows - 1))
    col = min(col, self._max_col(row))
    self.cur_row = row
    self.cur_col = col
    self.hex_nibble = 0
```

Синхронизация скролла в sync_scroll гарантирует, что курсор всегда в видимой области. Если курсор ушёл выше top_row — подтягиваем верхнюю границу вверх. Если ниже видимого окна — сдвигаем вниз.

```python
def sync_scroll(self, visible: int) -> None:
    if self.cur_row < self.top_row:
        self.top_row = self.cur_row
    elif self.cur_row >= self.top_row + visible:
        self.top_row = self.cur_row - visible + 1
```

### Undo-redo

Это два дека с лимитом в 1000 записей. `_undo_stack` и `_redo_stack` — это deque с `maxlen=UNDO_LIMIT`. Каждая запись — датакласс `_UndoEntry`, хранящий строку, колонку, старое и новое значение байта.

Метод `_record_write` вызывается перед каждой записью. Он читает текущее значение байта, пишет новое, сохраняет entry в undo-стек и очищает redo-стек — любое новое изменение делает невозможным повтор старых отменённых действий:

```python
def _record_write(self, row: int, col: int, new_val: int) -> None:
    old_val = self.hf.read_byte(row * self.hf.width + col)
    self.hf.write_byte(row, col, new_val)
    entry = _UndoEntry(row=row, col=col, old_val=old_val, new_val=new_val)
    self._undo_stack.append(entry)
    self._redo_stack.clear()
```

undo выталкивает запись из undo-стека, возвращает байт к старому значению, помещает запись в redo-стек и перемещает курсор на изменённый байт. redo делает обратное. Статусная строка получает сообщение с hex-значением и смещением.

### Поиск

Поиск использует отдельный датакласс SearchState, он был указан ранее. Методы search_next и search_prev реализуют кольцевой поиск. Если дошли до конца файла — начинают с начала, и наоборот. При зацикливании в статус пишется «search wrapped to start/end». Найденное смещение сохраняется в last_offset, длина совпадения — в match_len. Эти два поля используются в ui.py для подсветки совпадений жёлтым фоном.

```python
def _apply_search_result(
    self, found: Optional[int], visible: int, wrapped_msg: str
) -> bool:
    if found is None:
        self.status = StatusMessage(
            f"not found: {self.search.query!r}", is_error=True
        )
        return False
    self.search.last_offset = found
    self.search.match_len = len(self.search.query)
    self.jump_to_offset(found, visible)
    return True

def search_next(self, visible: int) -> bool:
    if not self.search.query:
        return False
    start = self.cur_row * self.hf.width + self.cur_col + 1
    found = self.hf.find_bytes(self.search.query, start)
    if found is None:
        found = self.hf.find_bytes(self.search.query, 0)
        if found is not None:
            self.status = StatusMessage("search wrapped to start")
    return self._apply_search_result(found, visible, "search wrapped to start")

def search_prev(self, visible: int) -> bool:
    if not self.search.query:
        return False
    current = self.cur_row * self.hf.width + self.cur_col
    found = self.hf.find_bytes_backward(self.search.query, current)
    if found is None:
        found = self.hf.find_bytes_backward(self.search.query, self.hf.size)
        if found is not None:
            self.status = StatusMessage("search wrapped to end")
    return self._apply_search_result(found, visible, "search wrapped to end")
```

Полный исходный файл доступен по [ссылке](https://github.com/alexeev-prog/cbhe/blob/main/src/cbhe/state.py).

<a class="anchor" id="handlers"></a>
## Кейбинды: handlers.py

Модуль handlers превращает коды клавиш в вызовы методов EditorState. Логика разбита по режимам, и для каждого режима строится таблица соответствия — словарь, где ключом является код клавиши, а значением — лямбда с действием.

Для READ-режима строится таблица `_make_read_nav_table`:

```python
def _make_read_nav_table(state: EditorState, visible: int) -> dict[int, object]:
    return {
        KEY_DOWN: lambda: state.scroll(1, visible),
        KEY_UP: lambda: state.scroll(-1, visible),
        KEY_NPAGE: lambda: state.scroll(visible, visible),
        KEY_PPAGE: lambda: state.scroll(-visible, visible),
        KEY_HOME: lambda: setattr(state, "top_row", 0),
        KEY_END: lambda: setattr(
            state, "top_row", max(0, state.hf.total_rows - visible)
        ),
        ord("w"): state.cycle_width,
        ord("W"): state.cycle_width,
        ord("r"): lambda: state.set_mode(EditorMode.READ),
        ord("h"): lambda: state.set_mode(EditorMode.HEX),
        ord("a"): lambda: state.set_mode(EditorMode.ASCII),
    }
```

Для нормального режима HEX/ASCII добавляется навигация курсором, вход в редактирование, undo. Для режима редактирования — специальные клавиши (Esc для выхода, Backspace/Delete для удаления, undo/redo) и навигация. Сами таблицы строятся в `_make_panel_nav_table` и `_make_edit_special_table`.

Дублирование между `handle_hex_edit` и `handle_ascii_edit` устранено через общую функцию `_handle_edit_common`. Она принимает предикат допустимых символов и функцию-писатель, а всё остальное — навигация и специальные клавиши — обрабатывается одинаково:

```python
def _handle_edit_common(
    state: EditorState,
    key: int,
    visible: int,
    char_predicate: Callable[[int], bool],
    char_writer: Callable[[int], None],
) -> None:
    special = _make_edit_special_table(state, visible)
    nav_keys: dict[int, tuple[int, int]] = {
        KEY_DOWN: (1, 0), KEY_UP: (-1, 0),
        KEY_LEFT: (0, -1), KEY_RIGHT: (0, 1),
    }

    if key in special:
        special[key]()
    elif key in nav_keys:
        dr, dc = nav_keys[key]
        state.move_cursor(dr, dc)
        state.sync_scroll(visible)
    elif key == KEY_HOME:
        state.cur_col = 0
    elif key == KEY_END:
        state.cur_col = state._max_col(state.cur_row)
    elif char_predicate(key):
        char_writer(key)
        state.sync_scroll(visible)
```

Теперь `handle_hex_edit` и `handle_ascii_edit` — просто вызовы этой функции с разными предикатами:

```python
def handle_hex_edit(state, key, visible):
    _handle_edit_common(state, key, visible,
        char_predicate=lambda k: k in _HEX_CHARS,
        char_writer=lambda k: state.write_hex_nibble(_HEX_CHARS[k]))

def handle_ascii_edit(state, key, visible):
    _handle_edit_common(state, key, visible,
        char_predicate=lambda k: 32 <= k <= 126,
        char_writer=lambda k: state.write_ascii(chr(k)))
```

Словарь `_HEX_CHARS` вынесен на уровень модуля — он строится один раз и маппит коды символов 0–9, a–f, A–F в числовые значения нибблов:

```python
_HEX_CHARS: dict[int, int] = {
    **{ord(str(d)): d for d in range(10)},
    **{ord(c): v for c, v in zip("abcdef", range(10, 16))},
    **{ord(c): v for c, v in zip("ABCDEF", range(10, 16))},
}
```

Помимо обработки режимов, модуль содержит функции для поиска и перехода. `handle_goto` запрашивает hex-смещение через prompt ввода и вызывает `jump_to_offset`. При некорректном вводе в статус пишется ошибка.

`handle_search_ascii` запрашивает строку, кодирует в UTF-8, сохраняет запрос в `state.search` и ищет через `hf.find_ascii`. При успехе переходит к найденному смещению, при неудаче сообщает об ошибке.

`handle_search_hex` использует `_parse_hex_query` для разбора ввода. Пользователь может ввести hex-последовательность в любом формате: `ff d8 ff`, `FFD8FF`, `0xff 0xd8 0xff`. Токены разбиваются по пробелам, убирается префикс `0x`, нечётные токены дополняются нулём слева, затем всё конвертируется через `bytes.fromhex`. Если хоть один токен невалидный — возвращается ошибка с его указанием.

```python
def _parse_hex_query(raw: str) -> tuple[bytes | None, str]:
    tokens = raw.split()
    result = bytearray()
    for token in tokens:
        token = token.removeprefix("0x").removeprefix("0X")
        if len(token) % 2 != 0:
            token = "0" + token
        try:
            result.extend(bytes.fromhex(token))
        except ValueError:
            return None, f"invalid hex token: {token!r}"
    if not result:
        return None, "empty query"
    return bytes(result), ""
```

Одна из главных функций — это `dispatch_key`. Она принимает клавишу и возвращает `False`, если нужно выйти из программы. Порядок проверок соответствует приоритету: ресайз и сохранение обрабатываются до всего, выход — только вне режима редактирования, затем редактирование, интерпретация, переход, поиск и в конце — навигация в зависимости от режима.

```python
def dispatch_key(state: EditorState, stdscr: Any, key: int, visible: int) -> bool:
    if key == KEY_RESIZE:
        return True

    if key == KEY_CTRL_S:
        state.hf.save()
        state.status.text = "saved"
        state.status.is_error = False
        return True

    if not state.editing and key in QUIT_KEYS:
        return False

    if state.editing:
        if state.mode == EditorMode.HEX:
            handle_hex_edit(state, key, visible)
        elif state.mode == EditorMode.ASCII:
            handle_ascii_edit(state, key, visible)
        return True

    if key in INTERPRET_KEYS:
        state.toggle_interpret()
        return True

    if key in GOTO_KEYS:
        handle_goto(state, stdscr, visible)
        return True

    if key == SEARCH_ASCII_KEY:
        handle_search_ascii(state, stdscr, visible)
        return True

    if key == SEARCH_HEX_KEY:
        handle_search_hex(state, stdscr, visible)
        return True

    if key == SEARCH_NEXT_KEY:
        state.search_next(visible)
        return True

    if key == SEARCH_PREV_KEY:
        state.search_prev(visible)
        return True

    if state.mode == EditorMode.READ:
        return handle_read(state, key, visible)

    return handle_panel_normal(state, key, visible)
```

Полный исходный файл доступен по [ссылке](https://github.com/alexeev-prog/cbhe/blob/main/src/cbhe/handlers.py).

<a class="anchor" id="ui-rendering"></a>
## Рендеринг UI

Модуль отрисовки — самый объёмный. Он отвечает за всё, что мы видим на экране: строки, панели, статусы, подсказки, промпты. Модуль не хранит состояние — он получает EditorState и HexFile как параметры и рендерит их.

В основе всего лежит функция _addstr — обёртка над curses.addstr, которая обрезает строку по ширине окна и проглатывает ошибки отрисовки за границами:

```python
def _addstr(win: Any, y: int, x: int, text: str, attr: int = 0) -> int:
    h, w = win.getmaxyx()
    if y >= h or x >= w:
        return x
    text = text[: w - x - 1]
    if text:
        try:
            win.addstr(y, x, text, attr)
        except curses.error:
            pass
    return x + len(text)
```

Она возвращает новую x-координату, что позволяет выстраивать цепочки вывода без ручного подсчёта смещений.

Также тут и интеграция с colors.py — выбор цвета для каждого байта реализован в _byte_attr. Это чистая функция, которая по смещению, значению байта и состоянию редактора возвращает атрибут curses. Порядок проверок жёстко задаёт приоритет:

```python
def _byte_attr(
    offset: int,
    col: int,
    b: int,
    cursor_col: Optional[int],
    mirror_col: Optional[int],
    dirty_offsets: set[int],
    hf: HexFile,
    state: EditorState,
    use_hex_color: bool,
) -> int:
    if col == cursor_col:
        return curses.color_pair(PAIR_CURSOR)                 # 1. курсор
    if col == mirror_col:
        return curses.color_pair(PAIR_HIGHLIGHT)              # 2. зеркальная подсветка
    if offset in dirty_offsets:
        return curses.color_pair(PAIR_DIRTY)                  # 3. изменённый байт
    if _is_search_match(offset, state):
        return curses.color_pair(PAIR_SEARCH_MATCH)           # 4. совпадение поиска

    field_def = hf.get_field_at(offset)
    if field_def is not None:
        return field_color(field_def.ftype.name)              # 5. поле формата

    return hex_color(b) if use_hex_color else ascii_color(b)  # 6. градиент
```

Зеркальная подсветка (mirror_col) связывает две панели. Когда курсор находится в hex-панели, соответствующий байт в ASCII-панели подсвечивается жёлтым фоном — и наоборот. Координаты mirror-колонки вычисляются в _resolve_cursor_cols:

```python
def _resolve_cursor_cols(row, state):
    cursor = state.cursor
    if not cursor or cursor[0] != row:
        return None, None, None, None

    col = cursor[1]
    if state.mode == EditorMode.HEX:
        return col, None, None, col      # hex_cursor, ascii_cursor, hex_mirror, ascii_mirror
    if state.mode == EditorMode.ASCII:
        return None, col, col, None
    return None, None, None, None
```

Если курсор в hex, mirror в ASCII получает ту же колонку — и _byte_attr для этой колонки в ASCII-панели вернёт PAIR_HIGHLIGHT.

А функция draw_frame отрисовывает весь фрейм. Фанфакт: в первой версии эта функция была в `__init__.py`, но во славу SRP я решил, что ей место в ui.py.

```python
def draw_frame(stdscr: Any, state: EditorState) -> None:
    stdscr.erase()
    draw_header(stdscr, state.hf, state)
    draw_rows(stdscr, state)
    draw_interpret_panel(stdscr, state)
    draw_status(stdscr, state)
    draw_keybinds(stdscr, state)
    stdscr.refresh()
```

draw_hex_row рисует одну строку: адрес, разделитель, hex-панель, разделитель, ASCII-панель. Hex-панель рисуется в _draw_hex_part с группировкой по 4 байта и разделителем ╌ между группами. В режиме редактирования текущий ниббл подчёркивается и выделяется жирным:

```python
if idx == cursor_col and editing:
    hi_char = hi[hex_nibble]
    lo_char = hi[1 - hex_nibble]
    x = _addstr(win, y, x, hi_char, attr | curses.A_UNDERLINE | curses.A_BOLD)
    x = _addstr(win, y, x, lo_char, attr)
```

draw_rows проходит по всем видимым строкам и для каждой вызывает draw_hex_row. Строка, на которой находится фокус (в READ — top_row, в остальных режимах — cur_row), получает подсвеченный адрес через PAIR_HIGHLIGHT.

Статус-заголовок формирует строку вида:

```
  cbhe  HEX [I]    │  example.out  │  4.2 KiB  │  :16  │  PNG  │  1%
```

Режим, маркер интерпретации [I], если панель включена, маркер того, что файл обновлён, но не сохранён (`*`), имя файла, читаемый размер, ширина дампа, имя формата, процент просмотра. При редактировании заголовок меняет цвет на зелёный.

![Пример режима редактирования](https://habrastorage.org/webt/9a/11/26/9a11264a27300f82a3c4c7bb5cc3350a.png)

Кроме того, есть статусная строка:

```python
  off:00000010  dec:16  val:00  dec:  0  chr:·  │  Width [SIZE]         saved
```

Смещение в hex и dec, значение байта в hex, dec и символ. Если байт принадлежит полю формата — после разделителя выводится имя поля и его тип жёлтым. В правой части — статусное сообщение. Ошибки выводятся красным, обычные сообщения — приглушённым.

draw_interpret_panel рисует справа панель фиксированной ширины 28 символов с псевдографической рамкой. Внутри — список label/value, полученных из interpret_at.

![Панель интерпретации](https://habrastorage.org/webt/1a/1e/3a/1a1e3ac9827050588be14a8151c81db0.png)

Кроме того, есть подсказки по кейбиндам. draw_keybinds выводит в последней строке экрана подсказки, зависящие от режима. Для READ используется KEYBINDS_READ, для нормального режима HEX/ASCII — KEYBINDS_NORMAL, для редактирования — KEYBINDS_EDIT. Клавиши выделены жирным, описания — обычным шрифтом.

Полный исходный файл доступен по [ссылке](https://github.com/alexeev-prog/cbhe/blob/main/src/cbhe/ui.py).

<a class="anchor" id="interpret"></a>
## Интерпретация байт: interpret.py

Тут признаюсь: мне не хватало какой-то фишки для нашего редактора, кроме подсветки. Спустя небольшой брейншторм я выбрал интерпретацию байт. Модуль `interpret.py` отвечает на вопрос «чем может быть этот байт и его соседи?». Он берёт смещение в файле, читает несколько байт подряд и интерпретирует их как числа разных размеров и порядков байт, как битовый вектор и как UTF-8 строку.

![Панель интерпретации](https://habrastorage.org/webt/08/37/9e/08379e28ccde687ffaac3e417537e833.png)

Все интерпретации собраны в список _STRUCT_FORMATS — это кортежи из четырёх элементов: короткий ключ, human-readable метка, форматная строка для struct.unpack и размер в байтах:

```python
_STRUCT_FORMATS: list[tuple[str, str, str, int]] = [
    ("i8", "int8", ">b", 1),
    ("u8", "uint8", ">B", 1),
    ("i16le", "int16le", "<h", 2),
    ("i16be", "int16be", ">h", 2),
    ("u16le", "uint16le", "<H", 2),
    ("u16be", "uint16be", ">H", 2),
    ("i32le", "int32le", "<i", 4),
    ("i32be", "int32be", ">i", 4),
    ("u32le", "uint32le", "<I", 4),
    ("u32be", "uint32be", ">I", 4),
    ("i64le", "int64le", "<q", 8),
    ("i64be", "int64be", ">q", 8),
    ("u64le", "uint64le", "<Q", 8),
    ("u64be", "uint64be", ">Q", 8),
    ("f32le", "float32le", "<f", 4),
    ("f32be", "float32be", ">f", 4),
    ("f64le", "float64le", "<d", 8),
    ("f64be", "float64be", ">d", 8),
]
```

Для каждого формата читается блок байт нужного размера через _read_raw:

```python
def _read_raw(hf: HexFile, offset: int, length: int) -> Optional[bytes]:
    if offset + length > hf.size:
        return None
    chunks: list[int] = []
    for i in range(length):
        chunks.append(hf.read_byte(offset + i))
    return bytes(chunks)
```

Затем struct.unpack с соответствующей форматной строкой.

```python
def _interpret_struct(raw: bytes, fmt: str, is_float: bool) -> str:
    try:
        (v,) = struct.unpack(fmt, raw)
        return _fmt_float(v) if is_float else str(v)
    except struct.error:
        return "—"
```

Float-значения форматируются отдельно — _fmt_float обрабатывает NaN и ±Inf, для обычных чисел выводит до шести цифр.

```python
def _fmt_float(v: float) -> str:
    if v != v:
        return "NaN"
    if v == float("inf"):
        return "+Inf"
    if v == float("-inf"):
        return "-Inf"
    return f"{v:.6g}"
```

После числовых интерпретаций добавляется битовое представление первого байта и UTF-8 строки из 4 и 8 байт. UTF-8 декодируется с заменой непечатных символов на · — так же, как в основной ASCII-панели.

```python
def _interpret_utf8(raw: bytes) -> str:
    try:
        text = raw.decode("utf-8")
        printable = "".join(c if c.isprintable() else "·" for c in text)
        return repr(printable)
    except UnicodeDecodeError:
        return "—"
```

Функция interpret_at возвращает список кортежей (label, value) — готовый к отрисовке. Панель интерпретации в ui.py просто проходит по этому списку и выводит в два столбца.

```python
def interpret_at(hf: HexFile, offset: int) -> list[InterpretRow]:
    rows: list[InterpretRow] = []

    for _key, label, fmt, size in _STRUCT_FORMATS:
        is_float = fmt[-1] in ("f", "d")
        raw = _read_raw(hf, offset, size)
        value = _interpret_struct(raw, fmt, is_float) if raw is not None else "—"
        rows.append((label, value))

    raw1 = _read_raw(hf, offset, 1)
    if raw1 is not None:
        rows.append(("bits(1B)", _interpret_bits(raw1)))

    raw4 = _read_raw(hf, offset, 4)
    if raw4 is not None:
        rows.append(("utf8(4B)", _interpret_utf8(raw4)))

    raw8 = _read_raw(hf, offset, 8)
    if raw8 is not None:
        rows.append(("utf8(8B)", _interpret_utf8(raw8)))

    return rows
```

Полный исходный файл доступен по [ссылке](https://github.com/alexeev-prog/cbhe/blob/main/src/cbhe/interpret.py).

<a class="anchor" id="entry-point"></a>
## Точка входа

Я использовал для создания проекта команду `uv init --package`, так что в `__init__.py` функция main является точкой входа.

В pyproject.toml это выглядит так:

```toml
[project.scripts]
cbhe = "cbhe:main"
```

Сам код лежит по пути `src/cbhe`.

Модуль `__init__.py` делает три вещи: разбирает аргументы командной строки, загружает форматы и запускает главный цикл. Никакой логики отрисовки или состояния здесь нет — только склейка.

Функция parse_arguments создаёт парсер и выдаёт на выходе неймспейс с аргументами.

```python
def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Curses-based hex editor with interpretation and highlighting",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s file.bin                    # Open file with auto-detection
  %(prog)s --formats custom.json file.bin  # Load custom formats
  %(prog)s -f fmt1.json -f fmt2.json file.bin  # Multiple format files
  %(prog)s -w 32 file.bin              # Set initial width to 32
  %(prog)s -m hex file.bin             # Start in hex mode
        """,
    )

    parser.add_argument("file", help="File to open and edit")
    parser.add_argument(
        "-f",
        "--formats",
        action="append",
        dest="format_files",
        help="JSON file with custom format definitions (can be used multiple times)",
    )
    parser.add_argument(
        "-w",
        "--width",
        type=int,
        choices=[8, 16, 32],
        default=16,
        help="Initial bytes per row (default: 16)",
    )
    parser.add_argument(
        "-m",
        "--mode",
        choices=["read", "hex", "ascii"],
        default="read",
        help="Initial mode (default: read)",
    )
    parser.add_argument(
        "--no-auto-detect",
        action="store_true",
        help="Disable automatic format detection",
    )
    parser.add_argument(
        "--format-dir", help="Directory containing JSON format files (loads all *.json)"
    )

    return parser.parse_args()
```

Загрузка форматов происходит до входа в curses-режим. Сначала регистрируются встроенные форматы через register_builtins(), затем подгружаются пользовательские JSON из аргументов -f и --format-dir. Если указан --no-auto-detect, формат у HexFile принудительно зануляется после создания.

```python
def load_all_formats(args: argparse.Namespace) -> None:
    format_files: list[str] = []

    if args.format_files:
        format_files.extend(args.format_files)

    if args.format_dir and os.path.isdir(args.format_dir):
        json_files = glob.glob(os.path.join(args.format_dir, "*.json"))
        format_files.extend(json_files)
        print(f"Found {len(json_files)} format files in {args.format_dir}")

    register_builtins()

    if format_files:
        print(f"Loading formats from: {format_files}")
        load_custom_formats(format_files)
```

Главный цикл работает в синхронном режиме. Он минимально простой: он обновляет состояние, рендерит фрейм и обрабатывает нажатия клавиш.

```python
def run(stdscr: Any, args: argparse.Namespace) -> None:
    init_colors()
    setup(stdscr)

    hf = HexFile(args.file, width=args.width)

    if args.no_auto_detect:
        hf.file_format = None

    state = EditorState(hf=hf)
    state.set_mode(_MODE_MAP[args.mode])

    while True:
        visible = _visible_rows(stdscr)
        state.clamp_top(visible)
        draw_frame(stdscr, state)

        key = stdscr.getch()

        if not dispatch_key(state, stdscr, key, visible):
            break

        if key == KEY_RESIZE:
            clear(stdscr)


def main() -> None:
    args = parse_arguments()

    if not os.path.isfile(args.file):
        print(f"File not found: {args.file}")
        sys.exit(1)

    load_all_formats(args)
    run_with_wrapper(run, args)
```

Полный исходный файл доступен по [ссылке](https://github.com/alexeev-prog/cbhe/blob/main/src/cbhe/__init__.py).

<a class="anchor" id="practice"></a>
# Практика!

Наконец-то наш редактор работает. Для того чтобы показать конкретный юзкейс, я решил взять самую лёгкую задачку из мира реверса — изменение пароля в программе.

Напишем простую программу на C, которая запрашивает пароль и сравнивает его с «1234»:

```c
#include <stdio.h>
#include <string.h>

int main() {
    char password[20];

    printf("Enter password: ");
    scanf("%s", password);

    if (strcmp(password, "1234") == 0) {
        printf("Access granted\n");
    } else {
        printf("Access denied\n");
    }

    return 0;
}
```

После — компиляция: `gcc -o example example.c`.

Запустим:

```bash
 $ ./example
Enter password: 1111
Access denied

 $ ./example
Enter password: 1234
Access granted
```

И открываем бинарник в нашем редакторе: `cbhe example`:

![Открытый бинарник](https://habrastorage.org/webt/b9/26/5f/b9265fabe87cc0c7143a02c9f218b56c.png)

Нажимаем / для ASCII-поиска и вводим, к примеру, password. Редактор находит строку в секции `.rodata` и перебрасывает курсор к ней. В hex-панели видно: 31 32 33 34 («1234» в ASCII), а рядом 41 63 63 65 73 73 («Access granted»).

Переключаемся в ASCII-режим: a. Нажимаем e для входа в редактирование. Курсор стоит на 1, вводим 1. Курсор сдвигается, вводим 1, потом ещё 1, потом ещё 1. Строка «1234» превратилась в «1111». Изменённые байты подсвечены красным.

![Вводим...](https://habrastorage.org/webt/13/1b/06/131b063b2d3933f61ccc9ab9d8a530e6.png)

Нажимаем Ctrl+S для сохранения. Выходим: q.

![Готово!](https://habrastorage.org/webt/0b/f2/2b/0bf22b2a42d79bcba9c43c9a8cfa30e3.png)

Запускаем пропатченный бинарник:

```bash
$ ./example
Enter password: 1111
Access granted
```

Почему это работает? Строковые литералы в C помещаются компилятором в секцию только для чтения (.rodata в ELF, .rdata в PE). При запуске программа не проверяет целостность этой секции — она просто читает байты и сравнивает. Мы изменили эти байты на диске, и программа честно сравнивает введённую строку с новым значением.

В реальности всё сложнее. Современные компиляторы могут заинлайнить строки, хранить их в зашифрованном виде. Подписанные бинарники (Windows Authenticode, macOS Gatekeeper) не запустятся после модификации. Упаковщики (UPX) и обфускаторы перемешивают секции. Но для программ, скомпилированных простым gcc без флагов защиты, этот метод работает. И наш редактор с ASCII-поиском и прямым редактированием делает такую задачу тривиальной — не нужно считать смещения в уме или пользоваться отдельным просмотрщиком и отдельным hex-редактором.

<a class="anchor" id="conclusion"></a>

# Заключение

Это был невероятный путь. Мы прошли путь от понимания того, как байт раскладывается на два ниббла, до работающего TUI-редактора с тремя слоями подсветки, автоопределением форматов, поиском и панелью интерпретации.

Код написан с оглядкой на расширяемость: новые форматы добавляются через JSON, бекенд curses изолирован в двух модулях, логика отделена от отрисовки. Проект можно развивать в нескольких направлениях — от переписывания на абстракции для пущей чистоты до расширения функциональности. Можно портировать на C + ncurses или на Rust + ratatui.

Исходный код доступен в [репозитории](https://github.com/alexeev-prog/cbhe); вы можете изучить его подробнее.

Если вы заметили нюансы в коде, плохие паттерны или просто имеете своё мнение на этот счёт — я рад почитать ваши комментарии.

Эту статью я писал так, чтобы получился не просто гайд «сделай так-то, и будет так-то», а объяснение паттернов и функционала с приложением основной логики, а не всего кода.
