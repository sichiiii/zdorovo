# Решение проблем

## Нет значка в панели

Проверьте indicator-сервис:

```bash
systemctl --user status zdorovo-indicator.service
journalctl --user -u zdorovo-indicator.service -n 100
```

В GNOME без Ubuntu Dock может понадобиться расширение AppIndicator/KStatusNotifierItem.

## Приложения объединяются в «Другие приложения»

Проверьте расширение:

```bash
gnome-extensions info zdorovo@jabka.github.io
```

Если оно только что установлено, выйдите из GNOME и войдите снова. До этого
момента Zdorovo использует AT-SPI; приложения без accessibility-поддержки могут
определяться менее точно.

## Не появляются напоминания

Убедитесь, что сервис активен и таймеры не приостановлены:

```bash
systemctl --user status zdorovo.service
journalctl --user -u zdorovo.service -n 100
```

Напоминания не показываются во время бездействия, демонстрации экрана и, если это
включено в настройках, полноэкранного режима.

## Сброс состояния без удаления статистики

```bash
systemctl --user stop zdorovo.service
rm -f ~/.local/share/zdorovo/scheduler-state.json
systemctl --user start zdorovo.service
```

База `usage.sqlite3` при этом не меняется.

