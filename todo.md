TODO:
add notifications for admin actions/tasks (do not just fail silently)
add notifications for admins on submissions
add opt in notification system for users

PLANNED FEATURES:
hall of fame
show some sort of result summary in landing page

Workflow concept:

- admin creates a tournament, complete with all modules needed (this should be easier)
- users go to site, register/login and join opens tournament page that accepts predictions
- after module has concluded, fetch results, map them internally and calculate scores
- modules belonging to next stage, should be updated with correct data
- go back to stage 2 and repeat until no more stages/modules left
