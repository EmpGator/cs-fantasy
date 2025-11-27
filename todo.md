TODO:
hall of fame
swiss stage result table sort only works for points, not scores
show some sort of result summary in landing page
sometimes when clearing dream team input, reserverd teams/players are not cleared correctly
for ties in dream team, show all tying players in same cell

Workflow concept:

- admin creates a tournament, complete with all modules needed (this should be easier)
- users go to site, register/login and join opens tournament page that accepts predictions
- after module has concluded, fetch results, map them internally and calculate scores
- modules belonging to next stage, should be updated with correct data
- go back to stage 2 and repeat until no more stages/modules left
