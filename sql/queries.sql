-- 查看最近的匹配记录
SELECT
    matches.id,
    resumes.filename,
    jobs.source AS jd_source,
    matches.score,
    matches.level,
    matches.conclusion,
    matches.created_at
FROM matches
JOIN resumes ON matches.resume_id = resumes.id
JOIN jobs ON matches.job_id = jobs.id
ORDER BY matches.created_at DESC;

-- 查看高匹配候选人
SELECT
    resumes.filename,
    matches.score,
    matches.level,
    matches.matched_skills,
    matches.missing_skills
FROM matches
JOIN resumes ON matches.resume_id = resumes.id
WHERE matches.score >= 80
ORDER BY matches.score DESC;

-- 按匹配等级统计数量
SELECT
    level,
    COUNT(*) AS total
FROM matches
GROUP BY level
ORDER BY total DESC;
