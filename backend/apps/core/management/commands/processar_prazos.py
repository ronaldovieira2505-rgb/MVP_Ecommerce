import time

from django.core.management.base import BaseCommand

from apps.core.deadlines import process_deadlines


class Command(BaseCommand):
    help = "Aplica as transições por prazo da máquina de estados (idempotente)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--loop",
            type=int,
            metavar="SEGUNDOS",
            help="Repete o processamento a cada N segundos (uso em desenvolvimento).",
        )

    def _run_once(self):
        done = process_deadlines()
        if done:
            for action, count in sorted(done.items()):
                self.stdout.write(f"{action}: {count}")
        else:
            self.stdout.write("Nenhum prazo a processar.")

    def handle(self, *args, **options):
        interval = options["loop"]
        if interval is not None and interval < 1:
            self.stderr.write("--loop deve ser um número de segundos maior que zero.")
            return
        if interval is None:
            self._run_once()
            return
        try:
            while True:
                self._run_once()
                time.sleep(interval)
        except KeyboardInterrupt:
            self.stdout.write("Encerrado.")
