"""Read observed Korean Stable Array mission rows without sending game input."""

from statistics import mean

from .du_recognition import area_in_viewport, compact, MIN_CONFIDENCE, n150_area, rows_in_area


def mission_rows(rows, resolution, viewport):
    def in_area(area):
        return rows_in_area(rows, resolution, area_in_viewport(area, viewport))

    anchors = in_area(n150_area(40, 28, 100, 40))
    if sum(compact(text) == "안정적배열" for _, (text, _) in anchors) != 1:
        return []

    objectives = in_area(n150_area(250, 110, 450, 620))
    statuses = in_area(n150_area(878, 110, 112, 620))
    proximity = 28 / 768 * viewport[3] * resolution[1]
    results = []
    for status_box, (status, confidence) in statuses:
        if compact(status) != "진행중":
            continue
        status_y = mean(point[1] for point in status_box)
        same_row = [(box, text, score) for box, (text, score) in objectives
                    if abs(mean(point[1] for point in box) - status_y) <= proximity]
        if not same_row:
            continue
        same_row.sort(key=lambda item: (item[0][0][1], item[0][0][0]))
        objective = " ".join(text for _, text, _ in same_row)
        token = compact(objective)
        action = None
        if "방정식1회전개" in token:
            action = "expand_equation"
        elif "가면을1회착용하고클리어" in token:
            action = "clear_with_mask"
        results.append({
            "objective": objective,
            "state": "in_progress",
            "confidence_status": "candidate" if min(confidence, *(score for _, _, score in same_row))
            >= MIN_CONFIDENCE else "low_confidence",
            "goal": action,
        })
    return results
