"""Мини-eval: прогоняет data/docs/*.txt и сравнивает с data/expected/*.json.

Отчёт: точность по каждому полю, галлюцинации (заполнено, а в эталоне null),
пропуски (null, а в эталоне есть значение).
"""


def main() -> None:
    # TODO: загрузка пар документ/эталон, прогон extract(), подсчёт метрик, печать отчёта
    raise NotImplementedError


if __name__ == "__main__":
    main()
