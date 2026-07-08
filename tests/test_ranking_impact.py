from benchcore.ranking_impact import TrialResult, leaderboard, ranking_impact


def test_leaderboard_ranks_by_average_reward():
    trials = [
        TrialResult("a", "sys1", 1.0, {}),
        TrialResult("b", "sys1", 0.0, {}),
        TrialResult("a", "sys2", 1.0, {}),
        TrialResult("b", "sys2", 1.0, {}),
    ]

    rows = leaderboard(trials)

    assert [(r.system_id, r.score, r.rank) for r in rows] == [
        ("sys2", 1.0, 1),
        ("sys1", 0.5, 2),
    ]


def test_ranking_impact_reports_score_and_rank_deltas():
    trials = [
        TrialResult("bad", "sys1", 0.0, {}),
        TrialResult("good", "sys1", 1.0, {}),
        TrialResult("neutral", "sys1", 0.5, {}),
        TrialResult("bad", "sys2", 1.0, {}),
        TrialResult("good", "sys2", 0.5, {}),
        TrialResult("neutral", "sys2", 0.5, {}),
    ]

    impact = ranking_impact(trials, {"bad"})

    assert impact["n_excluded_tasks"] == 1
    assert impact["excluded_tasks"] == ["bad"]
    assert impact["pairwise_flips"] == 1
    assert impact["kendall_tau"] == -1.0
    deltas = {row["system_id"]: row for row in impact["system_deltas"]}
    assert deltas["sys1"]["rank_delta"] == -1
    assert round(deltas["sys1"]["score_delta"], 6) == round(0.75 - 0.5, 6)
    assert deltas["sys2"]["rank_delta"] == 1
    assert round(deltas["sys2"]["score_delta"], 6) == round(0.5 - (2.0 / 3.0), 6)
