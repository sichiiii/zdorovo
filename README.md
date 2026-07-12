<p align="center">
  <img src="assets/io.github.jabka.Zdorovo.svg" width="112" alt="Zdorovo">
</p>

<h1 align="center">Zdorovo</h1>

<p align="center">
  Перерывы, дыхание и понятная статистика рабочего дня для GNOME.
</p>

<p align="center">
  <img alt="Release 0.1.0" src="https://img.shields.io/badge/release-0.1.0-327F79">
  <img alt="Python 3.10+" src="https://img.shields.io/badge/python-3.10%2B-327F79">
  <img alt="GNOME 46–50" src="https://img.shields.io/badge/GNOME-46%E2%80%9350-327F79">
  <img alt="Local data" src="https://img.shields.io/badge/data-local-327F79">
</p>

Zdorovo считает только активную работу за компьютером и предлагает короткие
паузы по расписанию. Упражнение можно начать с таймером, отложить или отключить.
Статистика приложений, отметки самочувствия и история занятий остаются на
компьютере.

## Что внутри

| | |
|---|---|
| **Рабочий ритм** | Паузы для глаз, движения, шеи и плеч; отдельное расписание для капель. |
| **Дыхание** | Три спокойных ритма без обязательных задержек дыхания. |
| **Привычки** | Небольшие дневные цели и необязательные напоминания. |
| **Достижения** | 22 многоуровневые эмблемы за регулярные паузы, дыхание и привычки. |
| **Аналитика** | Экранное время по дням, часам и приложениям; упражнения и самочувствие. |
| **Не мешает работе** | Таймеры стоят во время бездействия, полноэкранного режима и демонстрации экрана. |
| **Работает в фоне** | Пользовательский systemd-сервис и индикатор в панели Ubuntu. |

<table>
  <tr>
    <td width="33%"><img src="assets/eyes-guide.png" alt="Пауза для глаз"></td>
    <td width="33%"><img src="assets/general-guide.png" alt="Активная пауза"></td>
    <td width="33%"><img src="assets/breathing-guide.png" alt="Дыхательная пауза"></td>
  </tr>
  <tr>
    <td align="center">Глаза</td>
    <td align="center">Движение</td>
    <td align="center">Дыхание</td>
  </tr>
</table>

## Установка

### Debian-пакет

Скачайте `.deb` из раздела Releases и установите его через APT:

```bash
sudo apt install ./zdorovo_0.1.0_all.deb
```

После установки откройте **Zdorovo** из списка приложений. Сервисы запустятся
автоматически при следующем входе в GNOME.

### Из исходников

На Ubuntu 24.04 и новее:

```bash
sudo apt install \
  python3-gi python3-gi-cairo python3-cairo \
  gir1.2-gtk-4.0 gir1.2-adw-1 gir1.2-atspi-2.0 \
  gir1.2-gtk-3.0 gir1.2-ayatanaappindicator3-0.1 \
  gir1.2-graphene-1.0 at-spi2-core libglib2.0-bin

./install.sh
```

Установка из исходников размещает файлы только в `~/.local` и не требует root.

## Совместимость

| Система | Статус |
|---|---|
| Ubuntu 24.04 LTS и новее | Основная платформа |
| Debian 13 | Поддерживается Debian-пакетом |
| Другие GNOME-дистрибутивы | Запуск из исходников; индикатор зависит от Ayatana AppIndicator |
| GNOME 46–50 | Расширение отслеживания активного приложения |
| Wayland | Полный учёт приложений после включения расширения GNOME |
| X11 | Учёт через AT-SPI, расширение остаётся необязательным |

Расширение можно проверить и включить вручную:

```bash
gnome-extensions info zdorovo@jabka.github.io
gnome-extensions enable zdorovo@jabka.github.io
```

Иногда GNOME подхватывает новое расширение только после повторного входа в
сессию.

## Данные и приватность

Zdorovo не сохраняет заголовки окон, снимки экрана, адреса страниц и содержимое
документов.

| Данные | Путь |
|---|---|
| Настройки | `~/.config/zdorovo/config.json` |
| Статистика | `~/.local/share/zdorovo/usage.sqlite3` |
| Состояние таймеров | `~/.local/share/zdorovo/scheduler-state.json` |

Экспорт настроек, аналитики и открытых достижений доступен в самом приложении.
Импорт не удаляет исходный файл резервной копии.

## Разработка

```bash
python3 -m unittest discover -s tests -v
ruff check .
ruff format --check .
```

Сборка пакета:

```bash
./scripts/build-deb.sh
```

Устройство проекта описано в [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), а
типовые проблемы установки — в
[docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

## Удаление

Для локальной установки:

```bash
./uninstall.sh
```

Для Debian-пакета:

```bash
sudo apt remove zdorovo
```

Статистика и настройки при удалении сохраняются. Для полного сброса удалите
`~/.config/zdorovo` и `~/.local/share/zdorovo` вручную.

## Важно

Zdorovo помогает организовать рабочий ритм, но не является медицинским
устройством и не ставит диагнозы. Если упражнение усиливает боль, онемение,
головокружение или другие симптомы, остановитесь и обсудите ситуацию с врачом.

<p align="center">
  <small><a href="https://cyberjabka.by/">© CYBERJABKA</a></small>
</p>
