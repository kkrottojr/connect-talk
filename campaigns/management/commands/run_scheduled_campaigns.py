from django.core.management.base import BaseCommand

from campaigns.services import dispatch_due_campaigns


class Command(BaseCommand):
    help = (
        "Dispara (de forma simulada, respeitando o modo de envio configurado) todas "
        "as campanhas agendadas cuja data já passou, em todas as empresas. Não há um "
        "worker rodando sozinho no projeto — chame este comando periodicamente via "
        "cron/Task Scheduler para os agendamentos funcionarem sem intervenção manual."
    )

    def handle(self, *args, **options):
        dispatched = dispatch_due_campaigns()
        if not dispatched:
            self.stdout.write("Nenhum agendamento vencido.")
            return
        for campaign in dispatched:
            self.stdout.write(f"Disparada: {campaign.name} ({campaign.organization.name})")
        self.stdout.write(self.style.SUCCESS(f"{len(dispatched)} campanha(s) disparada(s)."))
