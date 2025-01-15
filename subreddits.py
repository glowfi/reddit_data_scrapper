from _typeshed import SupportsNext
import sys
import traceback
import logging
import random
import uuid
import json
import string
import datetime
from collections import defaultdict
from typing import TypedDict, Any


import requests
from requests.exceptions import HTTPError
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

from colorama import Fore, Style
from numerize import numerize
from dotenv import dotenv_values

from users import User, generate_user_info


class AccessTokenResponse(TypedDict):
    access_token: str
    token_type: str
    expires_in: int
    scope: str


class SubredditRule(TypedDict):
    short_name: str
    description: str


class FlairEmoji(TypedDict):
    text: str
    url: str


class FlairText(TypedDict):
    text: str


class SubredditFlair(TypedDict, total=False):
    rich_text: list[FlairEmoji | FlairText]
    full_text: str
    background_color: str  # hex color value


class Subreddit(TypedDict, total=False):
    id: str
    title: str
    public_description: str
    community_icon: str
    banner_background_image: str
    category: str
    rules: list[SubredditRule]
    flairs: list[SubredditFlair]  # *[oauth required]
    user_flairs: list[SubredditFlair]  # *[oauth required]
    key_color: str  # hex color value
    primary_color: str  # hex color value
    banner_background_color: str  # hex color value
    created_utc: int
    created_human: str
    subscribers: int
    subscribers_human: str
    members: list[User]
    moderators: list[User]  # list of [user id and name list]  * [oauth required]
    over18: bool
    spoilers_enabled: bool


class ResultState(TypedDict):
    status_code: int
    success: bool
    error: str


class SubredditResult(TypedDict):
    topic: str
    subreddits: Any | None
    result_state: ResultState


class SubredditRulesResult(TypedDict):
    subreddit: str
    rules: Any | None
    result_state: ResultState


class SubredditFlairsResult(TypedDict):
    subreddit: str
    flairs: Any | None
    result_state: ResultState


class SubredditModeratorsResult(TypedDict):
    subreddit: str
    moderators: Any | None
    result_state: ResultState


TOPICS = [
    "Activism",
    "AddictionSupport",
    "Animals and Pets",
    "Art",
    "Beauty and Makeup",
    "Business,Economics,and Finance",
    "Careers",
    "Cars and MotorVehicles",
    "Celebrity",
    "Crafts and DIY",
    "Crypto",
    "Culture,Race,and Ethnicity",
    "Ethics and Philosophy",
    "Family and Relationships",
    "Fashion",
    "Fitness and Nutrition",
    "Food and Drink",
    "Funny/Humor",
    "Gaming",
    "Gender",
    "History",
    "Hobbies",
    "Home and Garden",
    "InternetCulture and Memes",
    "Law",
    "Learning and Education",
    "Marketplace and Deals",
    "MatureThemes and AdultContent",
    "Medical and MentalHealth",
    "Mens Health",
    "Meta/Reddit",
    "Military",
    "Movies",
    "Music",
    "Outdoors and Nature",
    "Place",
    "Podcasts and Streamers",
    "Politics",
    "Programming",
    "Reading,Writing,and Literature",
    "Religion and Spirituality",
    "Science",
    "SexualOrientation",
    "Sports",
    "TabletopGames",
    "Technology",
    "Television",
    "TraumaSupport",
    "Travel",
    "Womens Health",
    "World News",
]
# QPM = 85
# MINUTES = 60


# Set up logging
logging.basicConfig(
    filename="api_requests.log", level=logging.INFO, format="%(message)s"
)

# Load DOTENV
config = dotenv_values(".env")

# Credentials
client_id = config.get("client_id")
client_secret = config.get("client_secret")
username = config.get("username")
password = config.get("password")
TOTAL_SUBREDDITS_PER_TOPICS = config.get("TOTAL_SUBREDDITS_PER_TOPICS")
SUBREDDIT_SORT_FILTER = config.get(
    "SUBREDDIT_SORT_FILTER"
)  # Sort by -> relevance, hot, top, new, comments

if not client_id or not client_secret or not username or not password:
    raise Exception("please give credentials in .env file")

if not SUBREDDIT_SORT_FILTER or not TOTAL_SUBREDDITS_PER_TOPICS:
    raise Exception("please give subreddit sort filter and subreddits per topics")


# Get Human Readable Date [Unix epoch to human readable data]
def unix_epoch_to_human_readable(unixtime):
    dt = datetime.datetime.utcfromtimestamp(unixtime)

    # Get month as words using list indexing
    month_words = [
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ]
    month_num = dt.month - 1
    month = month_words[month_num]

    # Get day and year as words
    day = str(dt.day).capitalize()
    year = str(dt.year)

    # Print the result
    return f"{day} {month} {year}"


# Get Custom User agent string
def getUserAgent() -> str:
    letters = string.ascii_lowercase
    length = 10
    return f"User agent by {str(uuid.uuid4())}-" + "".join(
        random.choice(letters) for _ in range(length)
    )


# Get New Session
def getSession() -> requests.Session:
    session = requests.session()
    retries = Retry(
        total=5,
        # total=1,
        backoff_factor=2,  # Exponential backoff
        status_forcelist=[429, 500, 502, 503, 504, 443],
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("https://", adapter)
    return session


# Get Oauth token
def getToken(params: dict[str, str], headers: dict[str, str], timeout: int) -> str:
    if not client_id or not client_secret or not username or not password:
        return ""
    session = getSession()
    session.auth = (client_id, client_secret)
    resp: AccessTokenResponse = session.post(
        "https://www.reddit.com/api/v1/access_token",
        data=params,
        headers=headers,
        timeout=timeout,
    ).json()
    return resp["access_token"]


def buildSubredditModerators(raw_json: Any) -> list[User]:
    moderators: list[User] = []
    for moderator in raw_json.get("data", {}).get("children", []):
        moderators.append(
            generate_user_info(moderator["id"].replace("t2_", ""), moderator["name"])
        )

    return moderators


def buildSubredditRules(raw_json: Any) -> list[SubredditRule]:
    rules: list[SubredditRule] = []
    for rule in raw_json["rules"]:
        new_rule: SubredditRule = {
            "short_name": rule["short_name"],
            "description": rule["description"],
        }
        rules.append(new_rule)
    return rules


def fetchSubredditModerators(subreddit: str, token: str) -> SubredditModeratorsResult:
    session = getSession()

    try:
        response = session.get(
            f"https://oauth.reddit.com/r/{subreddit}/about/moderators.json",
            headers={
                "User-Agent": getUserAgent(),
                "Authorization": f"bearer {token}",
            },
        )
        response.raise_for_status()

        response_json = response.json()
        print(
            f"{Fore.GREEN}Success got moderators Status Code:{response.status_code} Subreddit Name:{subreddit}{Style.RESET_ALL}"
        )
        logging.info(
            f"Success got moderators Status Code:{response.status_code} Subreddit Name:{subreddit}"
        )
        return {
            "subreddit": subreddit,
            "moderators": response_json,
            "result_state": {
                "error": "",
                "success": True,
                "status_code": response.status_code,
            },
        }
    except Exception as err:
        code = -1
        if type(err) is HTTPError:
            code = err.response.status_code
        print(
            f"{Fore.RED}Fail to get moderators Status Code:{code} Subreddit name:{subreddit}{Style.RESET_ALL} Error :{err}"
        )
        logging.error(
            f"Fail to get moderators Status Code:{code} Subreddit name:{subreddit} Error :{err}"
        )
        return {
            "subreddit": subreddit,
            "moderators": None,
            "result_state": {
                "error": str(err),
                "success": False,
                "status_code": code,
            },
        }


def buildSubredditFlairs(raw_json: Any) -> list[SubredditFlair]:
    flairs: list[SubredditFlair] = []

    for flair in raw_json:
        newFlair: SubredditFlair = {
            "background_color": flair.get("background_color", "")
        }
        richtexts: list[FlairEmoji | FlairText] = []
        for richtext in flair.get("richtext", []):
            if richtext.get("e", "") == "text":
                flairText: FlairText = {"text": richtext.get("t", "")}
                richtexts.append(flairText)
            elif richtext.get("e", "") == "emoji":
                flairEmoji: FlairEmoji = {
                    "text": richtext.get("a", ""),
                    "url": richtext.get("u", ""),
                }
                richtexts.append(flairEmoji)
        if richtexts:
            newFlair["rich_text"] = richtexts
        if flair.get("text", ""):
            newFlair["full_text"] = flair.get("text", "")
        if newFlair:
            flairs.append(newFlair)

    return flairs


def fetchSubredditFlairsUser(subreddit: str, token: str) -> SubredditFlairsResult:
    session = getSession()

    try:
        response = session.get(
            f"https://oauth.reddit.com/r/{subreddit}/api/user_flair_v2",
            headers={
                "User-Agent": getUserAgent(),
                "Authorization": f"bearer {token}",
            },
        )
        response.raise_for_status()

        response_json = response.json()
        print(
            f"{Fore.GREEN}Success got user flairs Status Code:{response.status_code} Subreddit Name:{subreddit}{Style.RESET_ALL}"
        )
        logging.info(
            f"Success got user flairs Status Code:{response.status_code} Subreddit Name:{subreddit}"
        )
        return {
            "subreddit": subreddit,
            "flairs": response_json,
            "result_state": {
                "error": "",
                "success": True,
                "status_code": response.status_code,
            },
        }
    except Exception as err:
        code = -1
        if type(err) is HTTPError:
            code = err.response.status_code
        print(
            f"{Fore.RED}Fail to get user flairs Status Code:{code} Subreddit name:{subreddit}{Style.RESET_ALL} Error :{err}"
        )
        logging.error(
            f"Fail to get user flairs Status Code:{code} Subreddit name:{subreddit} Error :{err}"
        )
        return {
            "subreddit": subreddit,
            "flairs": None,
            "result_state": {
                "error": str(err),
                "success": False,
                "status_code": code,
            },
        }


def fetchSubredditFlairs(subreddit: str, token: str) -> SubredditFlairsResult:
    session = getSession()

    try:
        response = session.get(
            f"https://oauth.reddit.com/r/{subreddit}/api/link_flair_v2",
            headers={
                "User-Agent": getUserAgent(),
                "Authorization": f"bearer {token}",
            },
        )
        response.raise_for_status()

        response_json = response.json()
        print(
            f"{Fore.GREEN}Success got flairs Status Code:{response.status_code} Subreddit Name:{subreddit}{Style.RESET_ALL}"
        )
        logging.info(
            f"Success got flairs Status Code:{response.status_code} Subreddit Name:{subreddit}"
        )
        return {
            "subreddit": subreddit,
            "flairs": response_json,
            "result_state": {
                "error": "",
                "success": True,
                "status_code": response.status_code,
            },
        }
    except Exception as err:
        code = -1
        if type(err) is HTTPError:
            code = err.response.status_code
        print(
            f"{Fore.RED}Fail to get flairs Status Code:{code} Subreddit name:{subreddit}{Style.RESET_ALL} Error :{err}"
        )
        logging.error(
            f"Fail to get flairs Status Code:{code} Subreddit name:{subreddit} Error :{err}"
        )
        return {
            "subreddit": subreddit,
            "flairs": None,
            "result_state": {
                "error": str(err),
                "success": False,
                "status_code": code,
            },
        }


def fetchSubredditRules(subreddit: str, token: str) -> SubredditRulesResult:
    session = getSession()

    try:
        if token:
            response = session.get(
                f"https://oauth.reddit.com/r/{subreddit}/about/rules.json",
                headers={
                    "User-Agent": getUserAgent(),
                    "Authorization": f"bearer {token}",
                },
            )
        else:
            response = session.get(
                f"https://reddit.com/r/{subreddit}/about/rules.json",
                headers={
                    "User-Agent": getUserAgent(),
                },
            )
        response.raise_for_status()

        response_json = response.json()
        print(
            f"{Fore.GREEN}Success got rules Status Code:{response.status_code} Subreddit Name:{subreddit}{Style.RESET_ALL}"
        )
        logging.info(
            f"Success got rules Status Code:{response.status_code} Subreddit Name:{subreddit}"
        )
        return {
            "subreddit": subreddit,
            "rules": response_json,
            "result_state": {
                "error": "",
                "success": True,
                "status_code": response.status_code,
            },
        }
    except Exception as err:
        code = -1
        if type(err) is HTTPError:
            code = err.response.status_code
        print(
            f"{Fore.RED}Fail to get rules Status Code:{code} Subreddit name:{subreddit}{Style.RESET_ALL} Error :{err}"
        )
        logging.error(
            f"Fail to get rules Status Code:{code} Subreddit name:{subreddit} Error :{err}"
        )
        return {
            "subreddit": subreddit,
            "rules": None,
            "result_state": {
                "error": str(err),
                "success": False,
                "status_code": code,
            },
        }


def fetchSubredditsByTopic(
    filter: str, limit: int, topic: str, token: str
) -> SubredditResult:
    session = getSession()

    # Sort by -> relevance, hot, top, new, comments

    try:
        if token:
            response = session.get(
                "https://oauth.reddit.com/search.json",
                headers={
                    "User-Agent": getUserAgent(),
                    "Authorization": f"bearer {token}",
                },
                params={
                    "q": topic,
                    "sort": filter,
                    "sr_detail": True,
                    "limit": limit,
                },
            )
        else:
            response = session.get(
                "https://reddit.com/search.json",
                headers={
                    "User-Agent": getUserAgent(),
                },
                params={
                    "q": topic,
                    "sort": filter,
                    "sr_detail": True,
                    "limit": limit,
                },
            )
        response.raise_for_status()

        response_json = response.json()
        print(
            f"{Fore.GREEN}Success Status Code:{response.status_code} Topic Name:{topic}{Style.RESET_ALL}"
        )
        logging.info(f"Success Status Code:{response.status_code} Topic Name:{topic}")
        return {
            "subreddits": response_json,
            "topic": topic,
            "result_state": {
                "error": "",
                "success": True,
                "status_code": response.status_code,
            },
        }
    except Exception as err:
        code = -1
        if type(err) is HTTPError:
            code = err.response.status_code
        print(
            f"{Fore.RED}Fail Status Code:{code} Topic name:{topic}{Style.RESET_ALL}  Error : {err}"
        )
        logging.error(f"Fail Status Code:{code} Topic name:{topic}  Error : {err}")
        return {
            "subreddits": None,
            "topic": topic,
            "result_state": {
                "error": str(err),
                "success": False,
                "status_code": code,
            },
        }


def buildSubreddit(
    raw_json: Any, topic: str, total_subreddits_per_topics: int
) -> list[Subreddit]:
    children = raw_json.get("data", {}).get("children", {})
    c = 0
    subreddits: list[Subreddit] = []
    seen_subreddit: set[str] = set()

    for child in children:
        if c == total_subreddits_per_topics:
            break

        subreddit_title = child.get("data", {}).get("subreddit_name_prefixed", "")
        if subreddit_title in seen_subreddit:
            continue
        seen_subreddit.add(subreddit_title)

        subreddit = child.get("data", {}).get("sr_detail")
        if (
            subreddit["subreddit_type"] == "private"
            or child.get("data", {}).get("subreddit_name_prefixed", "").find("u/") != -1
        ):
            continue
        else:
            new_subreddit: Subreddit = {}

            # Basic info
            new_subreddit["id"] = subreddit.get("name", "").replace("t5_", "")
            new_subreddit["title"] = child.get("data", {}).get(
                "subreddit_name_prefixed", ""
            )
            new_subreddit["public_description"] = subreddit.get(
                "public_description", ""
            )
            new_subreddit["community_icon"] = subreddit.get("community_icon", "")
            new_subreddit["banner_background_image"] = subreddit.get(
                "banner_background_image", ""
            )
            new_subreddit["category"] = topic

            # Colors
            new_subreddit["key_color"] = subreddit.get("key_color", "")
            new_subreddit["primary_color"] = subreddit.get("primary_color", "")
            new_subreddit["banner_background_color"] = subreddit.get(
                "banner_background_color", "#000000"
            )

            # Members,CreatedDate
            new_subreddit["created_utc"] = subreddit.get("created_utc", 0)
            new_subreddit["created_human"] = (
                unix_epoch_to_human_readable(int(new_subreddit["created_utc"]))
                if new_subreddit["created_utc"]
                else ""
            )
            new_subreddit["subscribers"] = subreddit.get("subscribers", 0)
            new_subreddit["subscribers_human"] = (
                numerize.numerize(int(new_subreddit["subscribers"]))
                if new_subreddit["subscribers"]
                else ""
            )
            new_subreddit["members"] = []

            # Spolier , NSFW
            new_subreddit["over18"] = subreddit.get("over18", False)
            new_subreddit["spoilers_enabled"] = subreddit.get("spoilers_enabled", False)

            subreddits.append(new_subreddit)

            c += 1

    return subreddits


def writeResult(
    id: str,
    result: ResultState,
):
    with open("request_status.txt", "a") as f:
        f.write(
            f"{id}, Status Code: {result['status_code']}, Success: {result['success']}, Error: {result['error']}\n"
        )
        f.write("\n")


# returns list of name of subreddits
# def getSubredditsRelevantToTopics(acc_token: str):
#     offset = min(QPM, len(topics))
#     startIdx = 0
#     endIdx = startIdx + offset

#     while endIdx <= len(topics):

#         results: list[SubredditResult] = []

#         with concurrent.futures.ThreadPoolExecutor(
#             max_workers=(endIdx - startIdx)
#         ) as executor:
#             futures = {
#                 executor.submit(
#                     fetchSubredditsByTopic,
#                     topic,
#                     acc_token,
#                 ): topic
#                 for topic in (topics[startIdx:endIdx])
#             }
#             for future in concurrent.futures.as_completed(futures):
#                 try:
#                     result = future.result()
#                     topic = result["topic"]
#                     buildSubredditInfo(result["subreddits"], topic)
#                     results.append(result)
#                 except Exception:
#                     print("Moving to next topic ...")

#         with open("request_status.txt", "a") as f:
#             for result in results:
#                 f.write(
#                     f"Topic: {result['topic']}, Status Code: {result['status_code']}, Success: {result['success']}, Error: {result['error']}\n"
#                 )
#             f.write("\n")
#         startIdx = endIdx
#         endIdx = startIdx + offset
#         if endIdx <= len(topics):
#             break
#         time.sleep(MINUTES)


def run():
    params = {
        "grant_type": "password",
        "username": username,
        "password": password,
    }
    headers = {"User-Agent": getUserAgent()}
    acc_token = getToken(params, headers, 10)

    if not acc_token:
        sys.exit(1)

    # Get subreddits
    results: list[SubredditResult] = []
    subreddits: dict[str, list[Subreddit]] = defaultdict(list[Subreddit])

    for topic in TOPICS:
        try:
            res = fetchSubredditsByTopic(SUBREDDIT_SORT_FILTER, 100, topic, acc_token)
            results.append(res)
            subreddits[topic] = buildSubreddit(
                res["subreddits"], topic, TOTAL_SUBREDDITS_PER_TOPICS
            )
        except Exception as err:
            print(traceback.print_exc())
            print("Moving to next topic ...", err)
            sys.exit(1)

    with open("request_status.txt", "a") as f:
        for result in results:
            writeResult(result["topic"], result["result_state"])
        f.write("\n")

    # Rules
    results1: list[SubredditRulesResult] = []
    for topic in subreddits:
        for idx, _ in enumerate(subreddits[topic]):
            title = subreddits[topic][idx].get("title", "").replace("r/", "")
            try:
                raw_json_rules = fetchSubredditRules(title, acc_token)
                results1.append(raw_json_rules)
                if raw_json_rules.get("rules", ""):
                    subreddits[topic][idx]["rules"] = buildSubredditRules(
                        raw_json_rules.get("rules")
                    )
                else:
                    subreddits[topic][idx]["rules"] = []
            except Exception:
                print(traceback.print_exc())
                sys.exit(1)
    with open("request_status.txt", "a") as f:
        for result in results1:
            writeResult(result["subreddit"] + "rule", result["result_state"])
        f.write("\n")

    # Get Flairs
    results2: list[SubredditFlairsResult] = []
    for topic in subreddits:
        for idx, _ in enumerate(subreddits[topic]):
            title = subreddits[topic][idx].get("title", "").replace("r/", "")
            try:
                raw_json_flairs = fetchSubredditFlairs(title, acc_token)
                results2.append(raw_json_flairs)
                if raw_json_flairs.get("flairs", ""):
                    subreddits[topic][idx]["flairs"] = buildSubredditFlairs(
                        raw_json_flairs.get("flairs")
                    )
                else:
                    subreddits[topic][idx]["flairs"] = []
            except Exception:
                print(traceback.print_exc())
                sys.exit(1)
    with open("request_status.txt", "a") as f:
        for result in results2:
            writeResult(result["subreddit"] + "flair", result["result_state"])
        f.write("\n")

    # Get User Flairs
    results3: list[SubredditFlairsResult] = []
    for topic in subreddits:
        for idx, _ in enumerate(subreddits[topic]):
            title = subreddits[topic][idx].get("title", "").replace("r/", "")
            try:
                raw_json_user_flairs = fetchSubredditFlairsUser(title, acc_token)
                results3.append(raw_json_user_flairs)
                if raw_json_user_flairs.get("flairs", ""):
                    subreddits[topic][idx]["user_flairs"] = buildSubredditFlairs(
                        raw_json_user_flairs.get("flairs")
                    )
                else:
                    subreddits[topic][idx]["user_flairs"] = []
            except Exception:
                print(traceback.print_exc())
                sys.exit(1)
    with open("request_status.txt", "a") as f:
        for result in results3:
            writeResult(result["subreddit"] + "user-flair", result["result_state"])
        f.write("\n")

    # Get Moderators
    results4: list[SubredditModeratorsResult] = []
    for topic in subreddits:
        for idx, _ in enumerate(subreddits[topic]):
            title = subreddits[topic][idx].get("title", "").replace("r/", "")
            try:
                raw_json_moderators = fetchSubredditModerators(title, acc_token)
                results4.append(raw_json_moderators)
                if raw_json_moderators.get("moderators", ""):
                    subreddits[topic][idx]["moderators"] = buildSubredditModerators(
                        raw_json_moderators.get("moderators")
                    )
                else:
                    subreddits[topic][idx]["moderators"] = []
            except Exception:
                print(traceback.print_exc())
                sys.exit(1)
    with open("request_status.txt", "a") as f:
        for result in results4:
            writeResult(result["subreddit"] + "moderators", result["result_state"])
        f.write("\n")

    with open("subreddits.json", "w") as fp:
        sorted_subreddits = dict(sorted(subreddits.items()))
        json.dump(sorted_subreddits, fp)
