"""The 6.3 Capability Point Expenditure chart-of-record reader (game.cp_costs)."""
from game import cp_costs


def test_assault_cost_matches_the_63_chart():
    # 6.3: Phasing "Barrage and/or an Assault" = 5; Non-Phasing "...defend" = 3.
    assert cp_costs.assault_cost(phasing=True) == 5
    assert cp_costs.assault_cost(phasing=False) == 3


def test_break_off_costs_match_the_63_chart():
    # 6.3: Break Contact = 2, Disengage = 4 (the Engaged surcharge).
    assert cp_costs.break_contact_cost() == 2
    assert cp_costs.disengage_cost() == 4
