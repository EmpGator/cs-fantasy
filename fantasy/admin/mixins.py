from django.urls import reverse
from urllib.parse import urlencode


class ModuleStageAdminMixin:
    """
    A mixin for ModuleAdmin classes to allow for pre-population of the
    tournament field when adding a new stage from the module change form.
    """
    raw_id_fields = ('stage',)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        field = super().formfield_for_foreignkey(db_field, request, **kwargs)
        if db_field.name == "stage":
            object_id = request.resolver_match.kwargs.get('object_id')
            tournament_id = None

            if object_id:
                try:
                    module = self.model.objects.get(pk=object_id)
                    tournament_id = module.tournament_id
                except self.model.DoesNotExist:
                    pass
            elif 'tournament' in request.GET:
                tournament_id = request.GET['tournament']

            if tournament_id:
                add_url = reverse('admin:fantasy_stage_add')
                params = urlencode({'tournament': tournament_id})
                field.widget.add_related_url = f'{add_url}?{params}'

        return field
