from django.core.management.base import BaseCommand
from fantasy.services import fetcher, hltv_parser


class Command(BaseCommand):
    help = "Fetches HLTV tournament results and imports them into the database."

    def add_arguments(self, parser):
        parser.add_argument("url", type=str, help="The HLTV URL to fetch and parse.")

    def handle(self, *args, **options):
        url = options["url"]
        self.stdout.write(f"Fetching data from: {url}")

        html_content = fetcher.fetch_page(url)
        if html_content:
            parsed_data = hltv_parser.parse_match_page(html_content)
            if parsed_data:
                raise Exception("TODO: Implement import logic")
                self.stdout.write(self.style.SUCCESS(f"Successfully processed {url}"))
            else:
                self.stdout.write(self.style.ERROR(f"Failed to parse data from {url}"))
        else:
            self.stdout.write(self.style.ERROR(f"Failed to fetch content from {url}"))
