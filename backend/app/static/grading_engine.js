/**
 * Kisan Setu - In-Browser Grading Engine & On-Device 6-Stage Inference Pipeline
 * Implements pure Three-Bucket Agmark Grading matching the Python backend exactly.
 */

export const GRADING_RULES = {
  min_size_cm: 6.0,
  marker_side_cm: 5.0,
  defect_classes: ["good", "damaged", "rotten", "sprouted", "undersized"],
  version: "v2.0",
  lot_grade_rules: [
    { grade: "Grade A", threshold: 70.0 },
    { grade: "Defective", threshold: 30.0 },
    { grade: "URS", threshold: 0.0 }
  ]
};

export const STAGE_NAMES = [
  "image_quality_check",
  "marker_detection",
  "onion_detection",
  "size_measurement",
  "defect_detection",
  "grading"
];

/**
 * Assign an individual onion to one of three buckets:
 * - Grade A: class is 'good' AND diameter >= min_size_cm (default 6.0cm)
 * - URS: class is 'good' AND diameter < min_size_cm (or class is 'undersized')
 * - Defective: class is 'damaged', 'rotten', 'sprouted'
 */
export function determineOnionBucket(clsName, diameterCm, minSizeCm = 6.0) {
  const normClass = String(clsName || "good").toLowerCase().trim();
  const diam = diameterCm !== null && diameterCm !== undefined ? parseFloat(diameterCm) : 0.0;

  if (normClass === "good") {
    if (diam >= minSizeCm) {
      return "grade_a";
    }
    return "urs";
  } else if (normClass === "undersized") {
    return "urs";
  } else if (["damaged", "rotten", "sprouted"].includes(normClass)) {
    return "defective";
  }
  return "defective";
}

/**
 * Determine overall Lot Grade Label (e.g. "Grade A (75.0%)", "Defective (35.0%)", "URS (25.0%)")
 */
export function evaluateLotGrade(gradeAPct, defectivePct, ursPct) {
  if (gradeAPct >= 70.0) {
    return {
      lot_grade: "Grade A",
      lot_grade_label: `Grade A (${gradeAPct.toFixed(1)}%)`,
      lot_grade_pct: gradeAPct
    };
  } else if (defectivePct >= 30.0) {
    return {
      lot_grade: "Defective",
      lot_grade_label: `Defective (${defectivePct.toFixed(1)}%)`,
      lot_grade_pct: defectivePct
    };
  } else {
    return {
      lot_grade: "URS",
      lot_grade_label: `URS (${ursPct.toFixed(1)}%)`,
      lot_grade_pct: ursPct
    };
  }
}

/**
 * Compute three-bucket grade statistics for a list of detected onions.
 */
export function computeGrade(onions, rules = GRADING_RULES) {
  const minSizeCm = rules.min_size_cm || 6.0;
  const rawCounts = {
    good: 0,
    damaged: 0,
    rotten: 0,
    sprouted: 0,
    undersized: 0
  };

  const totalOnions = onions ? onions.length : 0;

  if (totalOnions === 0) {
    const defectBreakdown = {};
    for (const k of Object.keys(rawCounts)) {
      defectBreakdown[k] = { count: 0, pct: 0.0 };
    }
    return {
      grade_a_pct: 0.0,
      urs_pct: 0.0,
      defective_pct: 0.0,
      total_onions: 0,
      grade_a_count: 0,
      urs_count: 0,
      defective_count: 0,
      lot_grade: "N/A",
      lot_grade_label: "No Onions",
      lot_grade_pct: 0.0,
      defect_breakdown: defectBreakdown,
      raw_counts: rawCounts,
      rule_version: rules.version || "v2.0",
      status: "no_onions"
    };
  }

  let gradeACount = 0;
  let ursCount = 0;
  let defectiveCount = 0;

  for (const onion of onions) {
    const cls = String(onion.class || onion.current_class || "good").toLowerCase().trim();
    const diamVal = parseFloat(onion.diameter_cm) || 0.0;
    const bucket = determineOnionBucket(cls, diamVal, minSizeCm);

    if (bucket === "grade_a") {
      gradeACount++;
      rawCounts.good = (rawCounts.good || 0) + 1;
    } else if (bucket === "urs") {
      ursCount++;
      if (cls === "good") {
        rawCounts.undersized = (rawCounts.undersized || 0) + 1;
      } else {
        rawCounts[cls] = (rawCounts[cls] || 0) + 1;
      }
    } else {
      defectiveCount++;
      if (rawCounts[cls] !== undefined) {
        rawCounts[cls]++;
      } else {
        rawCounts.damaged = (rawCounts.damaged || 0) + 1;
      }
    }
  }

  const gradeAPct = Math.round((gradeACount / totalOnions) * 1000) / 10;
  const defectivePct = Math.round((defectiveCount / totalOnions) * 1000) / 10;
  // Exact 100% sum constraint: URS absorbs rounding
  const ursPct = Math.round((100.0 - gradeAPct - defectivePct) * 10) / 10;

  const lotGradeEval = evaluateLotGrade(gradeAPct, defectivePct, ursPct);

  const defectBreakdown = {};
  for (const [k, count] of Object.entries(rawCounts)) {
    defectBreakdown[k] = {
      count: count,
      pct: Math.round((count / totalOnions) * 1000) / 10
    };
  }

  return {
    grade_a_pct: gradeAPct,
    urs_pct: ursPct,
    defective_pct: defectivePct,
    total_onions: totalOnions,
    grade_a_count: gradeACount,
    urs_count: ursCount,
    defective_count: defectiveCount,
    lot_grade: lotGradeEval.lot_grade,
    lot_grade_label: lotGradeEval.lot_grade_label,
    lot_grade_pct: lotGradeEval.lot_grade_pct,
    defect_breakdown: defectBreakdown,
    raw_counts: rawCounts,
    rule_version: rules.version || "v2.0",
    status: "ok"
  };
}

/**
 * Check image blur client-side using simple edge intensity variance.
 */
export function checkClientBlur(canvas) {
  const ctx = canvas.getContext("2d");
  const imgData = ctx.getImageData(0, 0, canvas.width, canvas.height);
  const data = imgData.data;
  const len = data.length;

  let totalDiff = 0;
  let count = 0;
  // Sample every 4th pixel for speed
  for (let i = 0; i < len - 16; i += 16) {
    const gray1 = (data[i] + data[i + 1] + data[i + 2]) / 3;
    const gray2 = (data[i + 4] + data[i + 5] + data[i + 6]) / 3;
    totalDiff += Math.abs(gray1 - gray2);
    count++;
  }

  const avgEdge = count > 0 ? totalDiff / count : 0;
  // Blur score threshold: < 3.0 indicates low edge definition (very blurry)
  const isBlurry = avgEdge < 3.0;
  return { isBlurry, score: avgEdge };
}

/**
 * On-Device Inference Pipeline Simulation (matches 6-stage server pipeline)
 */
export async function runOnDeviceInference(canvas, onStageProgress = null) {
  const width = canvas.width || 640;
  const height = canvas.height || 480;

  const stages = [
    { name: "image_quality_check", percent: 15, msg: "Image sharpness verified" },
    { name: "marker_detection", percent: 30, msg: "ArUco reference marker detected (5.0 cm)" },
    { name: "onion_detection", percent: 55, msg: "Onion contours localized" },
    { name: "size_measurement", percent: 70, msg: "Physical diameters calibrated" },
    { name: "defect_detection", percent: 85, msg: "Defect classifiers evaluated" },
    { name: "grading", percent: 100, msg: "Three-bucket grading calculated" }
  ];

  for (let i = 0; i < stages.length; i++) {
    const s = stages[i];
    if (onStageProgress) {
      onStageProgress({
        currentStage: s.name,
        stageIndex: i,
        totalStages: stages.length,
        percent: s.percent,
        message: s.msg
      });
    }
    // Small realistic delay for UI animation
    await new Promise(r => setTimeout(r, 220));
  }

  // Generate synthetic detections with realistic bounding boxes and sizes
  const numOnions = 7 + Math.floor(Math.random() * 5);
  const classes = ["good", "good", "good", "good", "undersized", "damaged", "sprouted"];
  const detections = [];

  for (let i = 0; i < numOnions; i++) {
    const sizePx = 60 + Math.random() * 50;
    const x1 = Math.max(20, Math.min(width - sizePx - 20, Math.random() * (width - sizePx)));
    const y1 = Math.max(20, Math.min(height - sizePx - 20, Math.random() * (height - sizePx)));
    const x2 = x1 + sizePx;
    const y2 = y1 + sizePx;

    const cls = classes[Math.floor(Math.random() * classes.length)];
    const diam = cls === "undersized" ? 3.5 + Math.random() * 2.2 : 5.8 + Math.random() * 3.5;
    const conf = 0.88 + Math.random() * 0.11;
    const bucket = determineOnionBucket(cls, diam, GRADING_RULES.min_size_cm);

    detections.push({
      id: i + 1,
      bbox: [Math.round(x1), Math.round(y1), Math.round(x2), Math.round(y2)],
      original_class: cls,
      current_class: cls,
      bucket: bucket,
      confidence: Math.round(conf * 100) / 100,
      diameter_cm: Math.round(diam * 10) / 10,
      is_overridden: false,
      computation_source: "device"
    });
  }

  const gradeResult = computeGrade(detections);

  return {
    detections,
    grade_result: gradeResult,
    is_device_computed: true,
    is_mock: true
  };
}
