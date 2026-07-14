"""Unified job spider with explicit real-data and demo fallback separation."""

from __future__ import annotations

import logging
import random
import re
import time
from dataclasses import dataclass, field

import requests

logger = logging.getLogger(__name__)

try:
    from bs4 import BeautifulSoup

    HAS_BS4 = True
except Exception:
    HAS_BS4 = False
    BeautifulSoup = None


@dataclass
class JobItem:
    title: str
    company: str
    location: str
    salary_range: str
    experience: str = ""
    education: str = ""
    raw_text: str = ""
    jd_summary: str = ""
    skill_tags: list[str] = field(default_factory=list)
    industry: str = ""
    source: str = "boss"
    source_url: str = ""
    external_id: str = ""

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "company": self.company,
            "location": self.location,
            "salary_range": self.salary_range,
            "experience": self.experience,
            "education": self.education,
            "raw_text": self.raw_text,
            "jd_summary": self.jd_summary,
            "skill_tags": self.skill_tags,
            "industry": self.industry,
            "source": self.source,
            "source_url": self.source_url,
            "external_id": self.external_id,
        }


_UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
]

_LAST_REQUEST_TIME = 0.0


def _rate_limit(min_interval: float = 1.0) -> None:
    global _LAST_REQUEST_TIME
    now = time.time()
    wait = min_interval - (now - _LAST_REQUEST_TIME)
    if wait > 0:
        time.sleep(wait)
    _LAST_REQUEST_TIME = time.time()


def _build_headers(referer: str = "") -> dict[str, str]:
    safe_referer = referer.encode("ascii", "ignore").decode("ascii") if referer else ""
    return {
        "User-Agent": random.choice(_UA_POOL),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": safe_referer,
        "Connection": "keep-alive",
    }


_MOCK_JOBS = {
    "python": [
        {
            "title": "Python后端开发工程师",
            "company": "字节跳动",
            "salary": "25K-45K·15薪",
            "location": "北京",
            "exp": "3-5年",
            "edu": "本科",
            "skills": ["Python", "FastAPI", "MySQL", "Redis", "Docker"],
            "industry": "互联网科技",
            "desc": "负责后端服务开发与接口治理，参与高并发系统优化。",
        },
        {
            "title": "AI后端工程师",
            "company": "阿里巴巴",
            "salary": "30K-55K·16薪",
            "location": "杭州",
            "exp": "3-5年",
            "edu": "硕士",
            "skills": ["Python", "PyTorch", "RAG", "向量数据库"],
            "industry": "人工智能",
            "desc": "负责 AI 平台后端开发与 RAG 应用落地。",
        },
    ],
    "frontend": [
        {
            "title": "前端开发工程师",
            "company": "腾讯",
            "salary": "20K-38K·15薪",
            "location": "深圳",
            "exp": "3-5年",
            "edu": "本科",
            "skills": ["Vue3", "React", "TypeScript", "Vite"],
            "industry": "互联网科技",
            "desc": "负责中后台与业务前台开发，推进组件化与工程化建设。",
        }
    ],
    "java": [
        {
            "title": "Java后端开发工程师",
            "company": "京东",
            "salary": "22K-40K·14薪",
            "location": "北京",
            "exp": "3-5年",
            "edu": "本科",
            "skills": ["Java", "Spring Boot", "MySQL", "Redis", "RocketMQ"],
            "industry": "电商",
            "desc": "负责交易系统后端开发与性能优化。",
        }
    ],
    "ai": [
        {
            "title": "大模型应用工程师",
            "company": "月之暗面",
            "salary": "40K-70K·16薪",
            "location": "北京",
            "exp": "3-5年",
            "edu": "硕士",
            "skills": ["LLM", "RAG", "Agent", "PyTorch"],
            "industry": "人工智能",
            "desc": "负责 LLM 应用开发、微调与评估闭环建设。",
        }
    ],
    "default": [
        {
            "title": "软件开发工程师",
            "company": "华为",
            "salary": "20K-40K·14薪",
            "location": "深圳",
            "exp": "3-5年",
            "edu": "本科",
            "skills": ["Java", "Python", "MySQL", "Redis"],
            "industry": "科技/通信",
            "desc": "负责核心产品研发，参与架构优化与系统交付。",
        }
    ],
}

_KEYWORD_MAP = {
    "python": ["python", "fastapi", "django", "flask"],
    "frontend": ["前端", "frontend", "vue", "react", "typescript", "javascript"],
    "java": ["java", "spring", "springboot", "springcloud"],
    "ai": ["ai", "大模型", "llm", "rag", "agent", "nlp", "机器学习"],
}


def _smart_mock(keyword: str, city: str) -> list[JobItem]:
    keyword_lower = (keyword or "").strip().lower()
    matched_key = "default"
    if keyword_lower in _MOCK_JOBS:
        matched_key = keyword_lower
    else:
        for key, aliases in _KEYWORD_MAP.items():
            if any(alias in keyword_lower for alias in aliases):
                matched_key = key
                break

    jobs = []
    for item in _MOCK_JOBS.get(matched_key, _MOCK_JOBS["default"]):
        jobs.append(
            JobItem(
                title=item["title"],
                company=item["company"],
                location=city or item["location"],
                salary_range=item["salary"],
                experience=item["exp"],
                education=item["edu"],
                raw_text=item["desc"],
                jd_summary=item["desc"][:200],
                skill_tags=item["skills"],
                industry=item["industry"],
                source="_mock",
            )
        )
    return jobs[:10]


class BossSpider:
    """BOSS直聘搜索适配器。"""

    BASE_URL = "https://www.zhipin.com"
    SEARCH_URL = "https://www.zhipin.com/web/geek/job"
    API_URL = "https://www.zhipin.com/wapi/zpgeek/search/joblist.json"

    CITY_CODES = {
        "北京": "101010100",
        "上海": "101020100",
        "广州": "101280100",
        "深圳": "101280600",
        "杭州": "101210100",
        "成都": "101270100",
        "南京": "101190100",
        "武汉": "101200100",
        "西安": "101110100",
        "长沙": "101250100",
        "苏州": "101190400",
        "重庆": "101040100",
    }

    def search(self, keyword: str, city: str = "", page: int = 1) -> tuple[list[JobItem], str]:
        city_code = self.CITY_CODES.get(city, "101010100")
        params = {"query": keyword, "city": city_code, "page": page}
        url = f"{self.SEARCH_URL}?query={keyword}&city={city_code}&page={page}"

        try:
            _rate_limit()
            headers = _build_headers(referer=f"{self.BASE_URL}/web/geek/job?query={keyword}")
            response_json = self._do_request(self.API_URL, params, headers)
            if response_json and response_json.get("zpData", {}).get("jobList"):
                return self._parse_api(response_json["zpData"]["jobList"]), ""

            jobs = self._parse_html(url, headers)
            if jobs:
                return jobs, ""
            return [], "boss search returned no jobs"
        except Exception as exc:
            logger.warning("BOSS search failed: %s", exc)
            return [], f"boss search failed: {exc}"

    def fetch_detail(self, url: str) -> JobItem | None:
        if not HAS_BS4:
            return None

        _rate_limit()
        response = requests.get(url, headers=_build_headers(referer=url), timeout=15)
        if response.status_code != 200:
            return None

        soup = BeautifulSoup(response.text, "html.parser")
        title_el = soup.select_one(".job-name") or soup.select_one(".name")
        company_el = soup.select_one(".company-info .name") or soup.select_one(".company-name")
        salary_el = soup.select_one(".salary")
        info_items = [item.get_text(" ", strip=True) for item in soup.select(".job-info-primary .info-primary p")]
        desc_el = soup.select_one(".job-sec-text") or soup.select_one(".job-detail-section")
        tag_items = [item.get_text(strip=True) for item in soup.select(".job-labels span")]

        title = title_el.get_text(strip=True) if title_el else ""
        company = company_el.get_text(strip=True) if company_el else ""
        salary = salary_el.get_text(strip=True) if salary_el else ""
        location = info_items[0] if len(info_items) > 0 else ""
        experience = info_items[1] if len(info_items) > 1 else ""
        education = info_items[2] if len(info_items) > 2 else ""
        description = desc_el.get_text("\n", strip=True) if desc_el else ""
        skill_tags = [item for item in tag_items if item][:8]

        if not any([title, company, description]):
            return None

        return JobItem(
            title=title or "未知岗位",
            company=company,
            location=location,
            salary_range=salary,
            experience=experience,
            education=education,
            raw_text=description,
            jd_summary=description[:200] if description else "",
            skill_tags=skill_tags,
            industry="",
            source="boss",
            source_url=url,
        )

    def _do_request(self, url: str, params: dict, headers: dict) -> dict | None:
        response = requests.get(url, params=params, headers=headers, timeout=15)
        if response.status_code == 200:
            return response.json()
        return None

    def _parse_api(self, job_list: list[dict]) -> list[JobItem]:
        jobs: list[JobItem] = []
        for item in job_list[:20]:
            try:
                job_id = item.get("jobId", "")
                description = item.get("jobDetail", {}).get("content", "") or item.get("jobDesc", "")
                job = JobItem(
                    title=self._clean(item.get("jobName", "")),
                    company=self._clean(item.get("brandName", "")),
                    location=self._clean(item.get("cityName", "")),
                    salary_range=self._clean(item.get("salaryDesc", "")),
                    experience=self._clean(item.get("experienceDesc", "")),
                    education=self._clean(item.get("educationDesc", "")),
                    raw_text=self._build_raw_text(item, description),
                    jd_summary=self._build_raw_text(item, description)[:200],
                    skill_tags=self._extract_skills(item.get("jobLabels", [])),
                    industry=self._clean(item.get("brandIndustry", "")),
                    source="boss",
                    source_url=f"{self.BASE_URL}/job_detail/{job_id}.html" if job_id else "",
                    external_id=str(job_id or ""),
                )
                jobs.append(job)
            except Exception:
                continue
        return jobs

    def _parse_html(self, url: str, headers: dict) -> list[JobItem]:
        if not HAS_BS4:
            return []

        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        jobs: list[JobItem] = []
        cards = soup.select(".job-card-wrapper") or soup.select(".job-list li")
        for card in cards[:20]:
            try:
                title_el = card.select_one(".job-name") or card.select_one("a")
                company_el = card.select_one(".company-name") or card.select_one(".name")
                salary_el = card.select_one(".salary") or card.select_one(".red")
                location_el = card.select_one(".job-area") or card.select_one(".area")
                title = title_el.get_text(strip=True) if title_el else ""
                if not title:
                    continue
                jobs.append(
                    JobItem(
                        title=title,
                        company=company_el.get_text(strip=True) if company_el else "",
                        location=location_el.get_text(strip=True) if location_el else "",
                        salary_range=salary_el.get_text(strip=True) if salary_el else "",
                        source="boss",
                    )
                )
            except Exception:
                continue
        return jobs

    @staticmethod
    def _clean(text: str) -> str:
        return re.sub(r"\s+", " ", text).strip() if text else ""

    @staticmethod
    def _extract_skills(labels: list) -> list[str]:
        skills: list[str] = []
        for label in labels or []:
            text = label.get("name", label.get("label", "")) if isinstance(label, dict) else str(label)
            if text:
                skills.append(text)
        return skills[:8]

    @staticmethod
    def _build_raw_text(item: dict, description: str = "") -> str:
        parts = [
            f"岗位: {item.get('jobName', '')}",
            f"公司: {item.get('brandName', '')}",
            f"薪资: {item.get('salaryDesc', '')}",
            f"地点: {item.get('cityName', '')}",
            f"经验: {item.get('experienceDesc', '')}",
            f"学历: {item.get('educationDesc', '')}",
        ]
        if description:
            parts.append(f"描述: {description[:500]}")
        return "\n".join(parts)


class JobSpider:
    """统一职位搜索入口。"""

    SPIDERS = {
        "boss": BossSpider(),
    }

    def search(self, keyword: str, city: str, source: str, page: int = 1) -> tuple[list[JobItem], str | None]:
        source = (source or "boss").strip().lower()
        if source == "all":
            jobs: list[JobItem] = []
            errors: list[str] = []
            for name, spider in self.SPIDERS.items():
                try:
                    sub_jobs, sub_error = spider.search(keyword, city, page)
                    jobs.extend(sub_jobs or [])
                    if sub_error:
                        errors.append(f"{name}: {sub_error}")
                except Exception as exc:
                    errors.append(f"{name}: {exc}")
            return jobs, "; ".join(errors) if errors else None

        spider = self.SPIDERS.get(source)
        if not spider:
            return [], f"unsupported source: {source}"
        return spider.search(keyword, city, page)

    def demo(self, keyword: str, city: str) -> tuple[list[JobItem], str]:
        return _smart_mock(keyword, city), "演示数据"

    def fetch_detail(self, source: str, url: str) -> JobItem | None:
        source = (source or "boss").strip().lower()
        spider = self.SPIDERS.get(source)
        if spider is None:
            return None
        return spider.fetch_detail(url)


_spider = JobSpider()


def get_spider() -> JobSpider:
    return _spider
