(function () {
  const form = document.getElementById("analysis-form");
  const panel = document.getElementById("progress-panel");
  const bar = document.getElementById("progress-bar");
  const title = document.getElementById("progress-title");
  const percent = document.getElementById("progress-percent");
  const submitButton = document.getElementById("submit-button");
  const aiCheckbox = form ? form.querySelector('input[name="enable_ai"]') : null;
  const reportAction = document.querySelector("[data-report-action]");
  const reportStatus = document.getElementById("report-status");
  const reportProgress = document.getElementById("report-progress");
  const reportProgressTitle = document.getElementById("report-progress-title");
  const reportProgressPercent = document.getElementById("report-progress-percent");
  const reportProgressBar = document.getElementById("report-progress-bar");
  const reportOutput = document.getElementById("report-output");
  const reportContent = document.getElementById("report-content");
  const clearableFiles = document.querySelectorAll("[data-clearable-file]");

  let timer = null;
  let stages = [];

  function getFileSummary(input) {
    if (!input || !input.files || input.files.length === 0) {
      return "";
    }

    if (input.files.length === 1) {
      return input.files[0].name;
    }

    return `已选择 ${input.files.length} 个文件`;
  }

  function updateFileControl(input) {
    const control = input.closest(".file-control");
    const clearButton = control ? control.querySelector("[data-clear-file]") : null;
    const selectedText = control ? control.querySelector("[data-selected-file]") : null;
    const summary = getFileSummary(input);

    if (clearButton) {
      clearButton.hidden = !summary;
    }

    if (selectedText) {
      selectedText.textContent = summary;
      selectedText.hidden = !summary;
    }
  }

  function bindFileControls() {
    clearableFiles.forEach((input) => {
      const control = input.closest(".file-control");
      if (!control) {
        return;
      }

      let selectedText = control.querySelector("[data-selected-file]");
      if (!selectedText) {
        selectedText = document.createElement("span");
        selectedText.className = "selected-file-text";
        selectedText.dataset.selectedFile = "true";
        selectedText.hidden = true;
        control.appendChild(selectedText);
      }

      const clearButton = control.querySelector("[data-clear-file]");
      input.addEventListener("change", () => updateFileControl(input));

      if (clearButton) {
        clearButton.addEventListener("click", (event) => {
          event.preventDefault();
          event.stopPropagation();
          input.value = "";
          updateFileControl(input);
          input.focus();
        });
      }

      updateFileControl(input);
    });
  }

  function buildStages() {
    const enableAi = Boolean(aiCheckbox && aiCheckbox.checked);
    return [
      { at: 10, label: "正在上传简历和 JD", step: "upload" },
      { at: 35, label: "正在读取文档内容", step: "parse" },
      { at: 62, label: "正在计算匹配分和短板", step: "score" },
      { at: 84, label: "正在生成 Word 和 Excel", step: "export" },
      {
        at: 94,
        label: enableAi ? "正在等待智能复核结果" : "正在整理并展示结果",
        step: "export",
      },
    ];
  }

  function setProgress(value) {
    const safeValue = Math.max(0, Math.min(value, 96));
    bar.style.width = `${safeValue}%`;
    percent.textContent = `${Math.round(safeValue)}%`;

    const currentStage = [...stages].reverse().find((stage) => safeValue >= stage.at);
    if (currentStage) {
      title.textContent = currentStage.label;
      document.querySelectorAll(".progress-steps li").forEach((item) => {
        item.classList.toggle("active", item.dataset.step === currentStage.step);
      });
    }
  }

  function startProgress() {
    let value = 4;
    stages = buildStages();
    panel.hidden = false;
    submitButton.disabled = true;
    submitButton.textContent = "处理中...";
    setProgress(value);
    panel.scrollIntoView({ behavior: "smooth", block: "center" });

    timer = window.setInterval(() => {
      const increment = value < 70 ? 5 : 1.5;
      value = Math.min(value + increment, 94);
      setProgress(value);
    }, 420);
  }

  async function readErrorMessage(response) {
    try {
      const data = await response.json();
      return data.detail || "汇总报告生成失败";
    } catch (error) {
      return "汇总报告生成失败，请检查服务日志或模型配置";
    }
  }

  function setReportProgress(value, label) {
    if (!reportProgressBar || !reportProgressPercent || !reportProgressTitle) {
      return;
    }

    const safeValue = Math.max(0, Math.min(value, 100));
    reportProgressBar.style.width = `${safeValue}%`;
    reportProgressPercent.textContent = `${Math.round(safeValue)}%`;
    if (label) {
      reportProgressTitle.textContent = label;
    }
  }

  function formatReportText(text) {
    const fragment = document.createDocumentFragment();
    const lines = String(text || "").split(/\r?\n/);
    let currentList = null;

    function closeList() {
      if (currentList) {
        fragment.appendChild(currentList);
        currentList = null;
      }
    }

    lines.forEach((rawLine) => {
      const line = rawLine.trim();
      if (!line) {
        closeList();
        return;
      }

      if (line.startsWith("### ")) {
        closeList();
        const heading = document.createElement("h4");
        heading.textContent = line.slice(4).trim();
        fragment.appendChild(heading);
        return;
      }

      if (line.startsWith("## ")) {
        closeList();
        const heading = document.createElement("h3");
        heading.textContent = line.slice(3).trim();
        fragment.appendChild(heading);
        return;
      }

      if (line.startsWith("# ")) {
        closeList();
        const heading = document.createElement("h3");
        heading.textContent = line.slice(2).trim();
        fragment.appendChild(heading);
        return;
      }

      if (line.startsWith("- ") || line.startsWith("* ")) {
        if (!currentList) {
          currentList = document.createElement("ul");
        }
        const item = document.createElement("li");
        item.textContent = line.slice(2).trim();
        currentList.appendChild(item);
        return;
      }

      closeList();
      const paragraph = document.createElement("p");
      paragraph.textContent = line;
      fragment.appendChild(paragraph);
    });

    closeList();
    return fragment;
  }

  async function generateReport(event) {
    event.preventDefault();
    if (!reportAction || !reportStatus || reportAction.classList.contains("is-busy")) {
      return;
    }

    const originalText = reportAction.textContent;
    let progressValue = 8;
    let reportTimer = null;
    reportAction.classList.add("is-busy");
    reportAction.textContent = "正在生成报告...";
    reportStatus.textContent = "正在生成候选人汇总报告。";
    reportStatus.classList.remove("error");
    if (reportProgress) {
      reportProgress.hidden = false;
    }
    if (reportOutput) {
      reportOutput.hidden = true;
    }
    if (reportContent) {
      reportContent.replaceChildren();
    }
    setReportProgress(progressValue, "正在整理候选人结果");

    reportTimer = window.setInterval(() => {
      const label =
        progressValue < 35
          ? "正在读取排名和短板"
          : progressValue < 72
            ? "正在生成汇总分析"
            : "正在组织报告内容";
      progressValue = Math.min(progressValue + (progressValue < 72 ? 7 : 2), 92);
      setReportProgress(progressValue, label);
    }, 520);

    try {
      const response = await fetch(reportAction.href);
      if (!response.ok) {
        throw new Error(await readErrorMessage(response));
      }

      const data = await response.json();
      if (!data.report) {
        throw new Error("汇总报告为空，请重新生成");
      }

      setReportProgress(100, "汇总报告已生成");
      reportStatus.textContent = "汇总报告已生成。";
      if (reportContent && reportOutput) {
        reportContent.replaceChildren(formatReportText(data.report));
        reportOutput.hidden = false;
        reportOutput.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    } catch (error) {
      reportStatus.textContent = error.message || "汇总报告生成失败";
      reportStatus.classList.add("error");
      setReportProgress(progressValue, "汇总报告生成失败");
    } finally {
      if (reportTimer) {
        window.clearInterval(reportTimer);
      }
      reportAction.classList.remove("is-busy");
      reportAction.textContent = originalText;
    }
  }

  if (reportAction) {
    reportAction.addEventListener("click", generateReport);
  }

  bindFileControls();

  if (!form || !panel || !bar || !title || !percent || !submitButton) {
    return;
  }

  form.addEventListener("submit", (event) => {
    const isLocalOnly = !Boolean(aiCheckbox && aiCheckbox.checked);
    if (isLocalOnly) {
      const confirmed = window.confirm(
        "本次将使用本地规则分析，不会调用 AI。确定开始分析吗？"
      );
      if (!confirmed) {
        event.preventDefault();
        return;
      }
    }

    if (timer) {
      window.clearInterval(timer);
    }
    startProgress();
  });

  window.addEventListener("pageshow", () => {
    if (timer) {
      window.clearInterval(timer);
    }
    panel.hidden = true;
    bar.style.width = "0%";
    percent.textContent = "0%";
    submitButton.disabled = false;
    submitButton.textContent = "一键处理";
  });
})();
