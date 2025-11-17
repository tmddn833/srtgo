try:
    from curl_cffi.requests.exceptions import ConnectionError
except ImportError:
    from requests.exceptions import ConnectionError

from datetime import datetime, timedelta
from json.decoder import JSONDecodeError
from random import gammavariate
from termcolor import colored
from typing import Awaitable, Callable, List, Optional, Tuple, Union

import asyncio
import click
import inquirer
from InquirerPy import inquirer as inquirer2
from InquirerPy.base.control import Choice

import keyring
import telegram
import time as Time
import re

try:
    from .ktx import (
        Korail,
        KorailError,
        ReserveOption,
        TrainType,
        AdultPassenger,
        ChildPassenger,
        SeniorPassenger,
        Disability1To3Passenger,
        Disability4To6Passenger,
    ) 
except ImportError:
    from ktx import (
        Korail,
        KorailError,
        ReserveOption,
        TrainType,
        AdultPassenger,
        ChildPassenger,
        SeniorPassenger,
        Disability1To3Passenger,
        Disability4To6Passenger,
    )

try:
    from .srt import (
        SRT,
        SRTError,
        SRTNetFunnelError,
        SeatType,
        Adult,
        Child,
        Senior,
        Disability1To3,
        Disability4To6,
    )
except ImportError:
    from srt import (
        SRT,
        SRTError,
        SRTNetFunnelError,
        SeatType,
        Adult,
        Child,
        Senior,
        Disability1To3,
        Disability4To6,
    )


STATIONS = {
    "SRT": [
        "수서",
        "동탄",
        "평택지제",
        "경주",
        "곡성",
        "공주",
        "광주송정",
        "구례구",
        "김천(구미)",
        "나주",
        "남원",
        "대전",
        "동대구",
        "마산",
        "목포",
        "밀양",
        "부산",
        "서대구",
        "순천",
        "여수EXPO",
        "여천",
        "오송",
        "울산(통도사)",
        "익산",
        "전주",
        "정읍",
        "진영",
        "진주",
        "창원",
        "창원중앙",
        "천안아산",
        "포항",
    ],
    "KTX": [
        "서울",
        "용산",
        "영등포",
        "광명",
        "수원",
        "천안아산",
        "오송",
        "대전",
        "서대전",
        "김천구미",
        "동대구",
        "경주",
        "포항",
        "밀양",
        "구포",
        "부산",
        "울산(통도사)",
        "마산",
        "창원중앙",
        "경산",
        "논산",
        "익산",
        "정읍",
        "광주송정",
        "목포",
        "전주",
        "순천",
        "여수EXPO",
        "청량리",
        "강릉",
        "행신",
        "정동진",
    ],
}
DEFAULT_STATIONS = {
    "SRT": ["수서", "대전", "동대구", "부산"],
    "KTX": ["서울", "대전", "동대구", "부산"],
}

# 예약 간격 (평균 간격 (초) = SHAPE * SCALE): gamma distribution (1.25 +/- 0.25 s)
RESERVE_INTERVAL_SHAPE = 4
RESERVE_INTERVAL_SCALE = 0.25
RESERVE_INTERVAL_MIN = 0.25

WAITING_BAR = ["|", "/", "-", "\\"]

RailType = Union[str, None]
ChoiceType = Union[int, None]

def tuple_choice_to_dict(choice: Tuple[str, str]) -> tuple:
    return Choice(name = choice[0], value= choice[1])

def tuple_list_to_choice_list(choices: List[Tuple[str, str]]) -> List[dict]:
    return [tuple_choice_to_dict(choice) for choice in choices]


@click.command()
@click.option("--debug", is_flag=True, help="Debug mode")
def srtgo(debug=False):
    MENU_CHOICES = [
        ("예매 시작", 1),
        ("예매 확인/결제/취소", 2),
        ("로그인 설정", 3),
        ("텔레그램 설정", 4),
        ("카드 설정", 5),
        ("역 설정", 6),
        ("역 직접 수정", 7),
        ("예매 옵션 설정", 8),
        ("나가기", -1),
    ]

    RAIL_CHOICES = [
        ("SRT","SRT"),
        ("KTX","KTX"),
        ("취소",-1),
    ]

    ACTIONS = {
        1: lambda rt: reserve(rt, debug),
        2: lambda rt: check_reservation(rt, debug),
        3: lambda rt: set_login(rt, debug),
        4: lambda _: set_telegram(),
        5: lambda _: set_card(),
        6: lambda rt: set_station(rt),
        7: lambda rt: edit_station(rt),
        8: lambda _: set_options(),
    }

    while True:
        choice = inquirer2.select(
            message="메뉴 선택 (↕(w,s):이동, Enter: 선택)", 
            choices=tuple_list_to_choice_list(MENU_CHOICES),
            keybindings={
                "up": [{"key": "w"}],       # w로 위
                "down": [{"key": "s"}],     # s로 아래
                "answer": [{"key": "enter"}],
                "interrupt": [{"key": "c"}],
            },
        ).execute()

        if choice == -1:
            break

        if choice in {1, 2, 3, 6, 7}:
            rail_type = inquirer2.select(
                message="열차 선택 (↕(w,s):이동, Enter: 선택, Ctrl-C: 취소)",
                choices=tuple_list_to_choice_list(RAIL_CHOICES),
                keybindings={
                    "up": [{"key": "w"}],       # w로 위
                    "down": [{"key": "s"}],     # s로 아래
                    "answer": [{"key": "enter"}],
                    "interrupt": [{"key": "c"}],
                },
            ).execute()
            if rail_type in {-1, None}:
                continue
        else:
            rail_type = None

        action = ACTIONS.get(choice)
        if action:
            action(rail_type)


def set_station(rail_type: RailType) -> bool:
    stations, default_station_key = get_station(rail_type)

    # Use InquirerPy checkbox; returns selected list directly
    try:
        selected = inquirer2.checkbox(
            message="역 선택 (↕(w,s):이동, Space: 선택, Enter: 완료, Ctrl-A: 전체선택, Ctrl-R: 선택해제, Ctrl-C: 취소)",
            choices=tuple_list_to_choice_list(stations),
            default=default_station_key,
            keybindings={
                "up": [{"key": "w"}],       # w로 위
                "down": [{"key": "s"}],     # s로 아래
                "answer": [{"key": "enter"}],
                "interrupt": [{"key": "c"}],
            },
        ).execute()
    except Exception:
        return False

    if not selected:
        print("선택된 역이 없습니다.")
        return False

    keyring.set_password(rail_type, "station", (selected_stations := ",".join(selected)))
    print(f"선택된 역: {selected_stations}")
    return True


def edit_station(rail_type: RailType) -> bool:
    stations, default_station_key = get_station(rail_type)
    try:
        station_text = inquirer.text(
            message="역 수정 (예: 수서,대전,동대구)",
            default=keyring.get_password(rail_type, "station") or "",
        ).execute()
    except Exception:
        return False

    if not station_text:
        print("선택된 역이 없습니다.")
        return False

    selected = [s.strip() for s in station_text.split(",")]

    # Verify all stations contain Korean characters
    hangul = re.compile("[가-힣]+")
    for station in selected:
        if not hangul.search(station):
            print(f"'{station}'는 잘못된 입력입니다. 기본 역으로 설정합니다.")
            selected = DEFAULT_STATIONS[rail_type]
            break

    keyring.set_password(
        rail_type, "station", (selected_stations := ",".join(selected))
    )
    print(f"선택된 역: {selected_stations}")
    return True


def get_station(rail_type: RailType) -> Tuple[List[str], List[int]]:
    stations = STATIONS[rail_type]
    station_key = keyring.get_password(rail_type, "station")

    if not station_key:
        return stations, DEFAULT_STATIONS[rail_type]

    valid_keys = [x for x in station_key.split(",")]
    return stations, valid_keys


def set_options():
    default_options = get_options()
    try:
        options_selected = inquirer2.checkbox(
            message="예매 옵션 선택 (↕(w,s):이동, Space: 선택, Enter: 완료, Ctrl-A: 전체선택, Ctrl-R: 선택해제, Ctrl-C: 취소)",
            choices=tuple_list_to_choice_list([
                ("어린이", "child"),
                ("경로우대", "senior"),
                ("중증장애인", "disability1to3"),
                ("경증장애인", "disability4to6"),
                ("KTX만", "ktx"),
            ]),
            keybindings={
                "up": [{"key": "w"}],       # w로 위
                "down": [{"key": "s"}],     # s로 아래
                "answer": [{"key": "enter"}],
                "interrupt": [{"key": "c"}],
            },
            default=default_options,
        ).execute()
    except Exception:
        return

    options = options_selected or []
    keyring.set_password("SRT", "options", ",".join(options))


def get_options():
    options = keyring.get_password("SRT", "options") or ""
    return options.split(",") if options else []


def set_telegram() -> bool:
    token = keyring.get_password("telegram", "token") or ""
    chat_id = keyring.get_password("telegram", "chat_id") or ""
    try:
        token = inquirer.text(
            message="텔레그램 token (Enter: 완료, Ctrl-C: 취소)",
            default=token,
        ).execute()
        chat_id = inquirer.text(
            message="텔레그램 chat_id (Enter: 완료, Ctrl-C: 취소)",
            default=chat_id,
        ).execute()
    except Exception:
        return False

    if not (token and chat_id):
        return False

    try:
        keyring.set_password("telegram", "ok", "1")
        keyring.set_password("telegram", "token", token)
        keyring.set_password("telegram", "chat_id", chat_id)
        tgprintf = get_telegram()
        asyncio.run(tgprintf("[SRTGO] 텔레그램 설정 완료"))
        return True
    except Exception as err:
        print(err)
        keyring.delete_password("telegram", "ok")
        return False


def get_telegram() -> Optional[Callable[[str], Awaitable[None]]]:
    token = keyring.get_password("telegram", "token")
    chat_id = keyring.get_password("telegram", "chat_id")

    async def tgprintf(text):
        if token and chat_id:
            bot = telegram.Bot(token=token)
            async with bot:
                await bot.send_message(chat_id=chat_id, text=text)

    return tgprintf


def set_card() -> None:
    card_info = {
        "number": keyring.get_password("card", "number") or "",
        "password": keyring.get_password("card", "password") or "",
        "birthday": keyring.get_password("card", "birthday") or "",
        "expire": keyring.get_password("card", "expire") or "",
    }
    try:
        number = inquirer.secret(
            message="신용카드 번호 (하이픈 제외(-), Enter: 완료, Ctrl-C: 취소)",
            default=card_info["number"],
        ).execute()
        password = inquirer.secret(
            message="카드 비밀번호 앞 2자리 (Enter: 완료, Ctrl-C: 취소)",
            default=card_info["password"],
        ).execute()
        birthday = inquirer.secret(
            message="생년월일 (YYMMDD) / 사업자등록번호 (Enter: 완료, Ctrl-C: 취소)",
            default=card_info["birthday"],
        ).execute()
        expire = inquirer.secret(
            message="카드 유효기간 (YYMM, Enter: 완료, Ctrl-C: 취소)",
            default=card_info["expire"],
        ).execute()
    except Exception:
        return

    card_info = {"number": number, "password": password, "birthday": birthday, "expire": expire}
    if card_info:
        for key, value in card_info.items():
            keyring.set_password("card", key, value)
        keyring.set_password("card", "ok", "1")


def pay_card(rail, reservation) -> bool:
    if keyring.get_password("card", "ok"):
        birthday = keyring.get_password("card", "birthday")
        return rail.pay_with_card(
            reservation,
            keyring.get_password("card", "number"),
            keyring.get_password("card", "password"),
            birthday,
            keyring.get_password("card", "expire"),
            0,
            "J" if len(birthday) == 6 else "S",
        )
    return False


def set_login(rail_type="SRT", debug=False):
    credentials = {
        "id": keyring.get_password(rail_type, "id") or "",
        "pass": keyring.get_password(rail_type, "pass") or "",
    }

    try:
        id_value = inquirer.text(
            message=f"{rail_type} 계정 아이디 (멤버십 번호, 이메일, 전화번호)",
            default=credentials["id"],
        ).execute()
        pass_value = inquirer.secret(
            message=f"{rail_type} 계정 패스워드",
            default=credentials["pass"],
        ).execute()
    except Exception:
        return False

    if not id_value or not pass_value:
        return False

    try:
        SRT(id_value, pass_value, verbose=debug) if rail_type == "SRT" else Korail(
            id_value, pass_value, verbose=debug
        )

        keyring.set_password(rail_type, "id", id_value)
        keyring.set_password(rail_type, "pass", pass_value)
        keyring.set_password(rail_type, "ok", "1")
        return True
    except SRTError as err:
        print(err)
        keyring.delete_password(rail_type, "ok")
        return False


def login(rail_type="SRT", debug=False):
    if (
        keyring.get_password(rail_type, "id") is None
        or keyring.get_password(rail_type, "pass") is None
    ):
        set_login(rail_type)

    user_id = keyring.get_password(rail_type, "id")
    password = keyring.get_password(rail_type, "pass")

    rail = SRT if rail_type == "SRT" else Korail
    return rail(user_id, password, verbose=debug)


def reserve(rail_type="SRT", debug=False):
    rail = login(rail_type, debug=debug)
    is_srt = rail_type == "SRT"

    # Get date, time, stations, and passenger info
    now = datetime.now() + timedelta(minutes=10)
    today = now.strftime("%Y%m%d")
    this_time = now.strftime("%H%M%S")

    defaults = {
        "departure": keyring.get_password(rail_type, "departure")
        or ("수서" if is_srt else "서울"),
        "arrival": keyring.get_password(rail_type, "arrival") or "동대구",
        "date": keyring.get_password(rail_type, "date") or today,
        "time": keyring.get_password(rail_type, "time") or "120000",
        "adult": int(keyring.get_password(rail_type, "adult") or 1),
        "child": int(keyring.get_password(rail_type, "child") or 0),
        "senior": int(keyring.get_password(rail_type, "senior") or 0),
        "disability1to3": int(keyring.get_password(rail_type, "disability1to3") or 0),
        "disability4to6": int(keyring.get_password(rail_type, "disability4to6") or 0),
    }

    # Set default stations if departure equals arrival
    if defaults["departure"] == defaults["arrival"]:
        defaults["arrival"] = (
            "동대구" if defaults["departure"] in ("수서", "서울") else None
        )
        defaults["departure"] = (
            defaults["departure"]
            if defaults["arrival"]
            else ("수서" if is_srt else "서울")
        )

    stations, station_key = get_station(rail_type)
    options = get_options()

    # Generate date and time choices
    date_choices = [
        (
            (now + timedelta(days=i)).strftime("%Y/%m/%d %a"),
            (now + timedelta(days=i)).strftime("%Y%m%d"),
        )
        for i in range(28)
    ]
    time_choices = [(f"{h:02d}", f"{h:02d}0000") for h in range(24)]

    # Ask for reservation info using InquirerPy select/text prompts
    try:
        departure = inquirer2.select(
            message="출발역 선택 (↕(w,s):이동, Enter: 선택, c: 취소)",
            choices=station_key,
            default=defaults["departure"],
            keybindings={
                "up": [{"key": "w"}],       # w로 위
                "down": [{"key": "s"}],     # s로 아래
                "answer": [{"key": "enter"}],
                "interrupt": [{"key": "c"}],
            },
        ).execute()

        arrival = inquirer2.select(
            message="도착역 선택 (↕(w,s):이동, Enter: 선택, Ctrl-C: 취소)",
            choices=station_key,
            default=defaults["arrival"],
            keybindings={
                "up": [{"key": "w"}],       # w로 위
                "down": [{"key": "s"}],     # s로 아래
                "answer": [{"key": "enter"}],
                "interrupt": [{"key": "c"}],
            },
        ).execute()

        date = inquirer2.select(
            message="출발 날짜 선택 (↕(w,s):이동, Enter: 선택, Ctrl-C: 취소)",
            choices=tuple_list_to_choice_list(date_choices),
            default=defaults["date"],
            keybindings={
                "up": [{"key": "w"}],       # w로 위
                "down": [{"key": "s"}],     # s로 아래
                "answer": [{"key": "enter"}],
                "interrupt": [{"key": "c"}],
            },
        ).execute()

        time = inquirer2.select(
            message="출발 시각 선택 (↕(w,s):이동, Enter: 선택, Ctrl-C: 취소)",
            choices=tuple_list_to_choice_list(time_choices),
            default=defaults["time"],
            keybindings={
                "up": [{"key": "w"}],       # w로 위
                "down": [{"key": "s"}],     # s로 아래
                "answer": [{"key": "enter"}],
                "interrupt": [{"key": "c"}],
            },
        ).execute()

        adult = inquirer2.select(
            message="성인 승객수 (↕(w,s):이동, Enter: 선택, Ctrl-C: 취소)",
            choices=list(range(10)),
            default=defaults["adult"],
            keybindings={
                "up": [{"key": "w"}],       # w로 위
                "down": [{"key": "s"}],     # s로 아래
                "answer": [{"key": "enter"}],
                "interrupt": [{"key": "c"}],
            },
        ).execute()
    except Exception as e:
        print(e)
        print(colored("예매 정보 입력 중 취소되었습니다", "green", "on_red") + "\n")
        return
    passenger_types = {
        "child": "어린이",
        "senior": "경로우대",
        "disability1to3": "1~3급 장애인",
        "disability4to6": "4~6급 장애인",
    }

    passenger_classes = {
        "adult": Adult if is_srt else AdultPassenger,
        "child": Child if is_srt else ChildPassenger,
        "senior": Senior if is_srt else SeniorPassenger,
        "disability1to3": Disability1To3 if is_srt else Disability1To3Passenger,
        "disability4to6": Disability4To6 if is_srt else Disability4To6Passenger,
    }

    PASSENGER_TYPE = {
        passenger_classes["adult"]: "어른/청소년",
        passenger_classes["child"]: "어린이",
        passenger_classes["senior"]: "경로우대",
        passenger_classes["disability1to3"]: "1~3급 장애인",
        passenger_classes["disability4to6"]: "4~6급 장애인",
    }

    # Add passenger-specific selections if requested
    info = {
        "departure": departure,
        "arrival": arrival,
        "date": date,
        "time": time,
        "adult": adult,
    }

    for key, label in passenger_types.items():
        if key in options:
            try:
                val = inquirer2.select(
                    message=f"{label} 승객수 (↕(w,s):이동, Enter: 선택, c: 취소)",
                    choices=list(range(10)),
                    default=defaults.get(key, 0),
                    keybindings={
                        "up": [{"key": "w"}],       # w로 위
                        "down": [{"key": "s"}],     # s로 아래
                        "answer": [{"key": "enter"}],
                        "interrupt": [{"key": "c"}],
                    },
                ).execute()
            except Exception:
                print(colored("예매 정보 입력 중 취소되었습니다", "green", "on_red") + "\n")
                return
            info[key] = val

    # Validate input info
    if info["departure"] == info["arrival"]:
        print(colored("출발역과 도착역이 같습니다", "green", "on_red") + "\n")
        return

    # Save preferences
    for key, value in info.items():
        keyring.set_password(rail_type, key, str(value))

    # Adjust time if needed
    if info["date"] == today and int(info["time"]) < int(this_time):
        info["time"] = this_time

    # Build passenger list
    passengers = []
    total_count = 0
    for key, cls in passenger_classes.items():
        if key in info and info[key] > 0:
            passengers.append(cls(info[key]))
            total_count += info[key]

    # Validate passenger count
    if not passengers:
        print(colored("승객수는 0이 될 수 없습니다", "green", "on_red") + "\n")
        return

    if total_count >= 10:
        print(colored("승객수는 10명을 초과할 수 없습니다", "green", "on_red") + "\n")
        return

    msg_passengers = [
        f"{PASSENGER_TYPE[type(passenger)]} {passenger.count}명"
        for passenger in passengers
    ]
    print(*msg_passengers)

    # Search for trains
    params = {
        "dep": info["departure"],
        "arr": info["arrival"],
        "date": info["date"],
        "time": info["time"],
        "passengers": [passenger_classes["adult"](total_count)],
        **(
            {"available_only": False}
            if is_srt
            else {
                "include_no_seats": True,
                **({"train_type": TrainType.KTX} if "ktx" in options else {}),
            }
        ),
    }

    trains = rail.search_train(**params)

    def train_decorator(train):
        msg = train.__repr__()
        return (
            msg.replace("예약가능", "가능")
            .replace("가능", "가능")
            .replace("신청하기", "가능")
        )

    if not trains:
        print(colored("예약 가능한 열차가 없습니다", "green", "on_red") + "\n")
        return


    # Get train selection
    try:
        selected_trains = inquirer2.checkbox(
            message="예약할 열차 선택 (↕:이동, Space: 선택, Enter: 완료, Ctrl-A: 전체선택, Ctrl-R: 선택해제, c: 취소)",
            choices=tuple_list_to_choice_list([(train_decorator(train), i) for i, train in enumerate(trains)]),
            default=None,
            keybindings={
                "up": [{"key": "w"}],       # w로 위
                "down": [{"key": "s"}],     # s로 아래
                "answer": [{"key": "enter"}],
                "interrupt": [{"key": "c"}],
            },
        ).execute()
    except Exception:
        print(colored("선택한 열차가 없습니다!", "green", "on_red") + "\n")
        return

    if not selected_trains:
        print(colored("선택한 열차가 없습니다!", "green", "on_red") + "\n")
        return

    n_trains = len(selected_trains)

    # Get seat type preference
    seat_type = SeatType if is_srt else ReserveOption
    try:
        type_choice = inquirer2.select(
            message="선택 유형",
            choices=tuple_list_to_choice_list([
                ("일반실 우선", seat_type.GENERAL_FIRST),
                ("일반실만", seat_type.GENERAL_ONLY),
                ("특실 우선", seat_type.SPECIAL_FIRST),
                ("특실만", seat_type.SPECIAL_ONLY),
            ]),
            keybindings={
                "up": [{"key": "w"}],       # w로 위
                "down": [{"key": "s"}],     # s로 아래
                "answer": [{"key": "enter"}],
                "interrupt": [{"key": "c"}],
            }
        ).execute()

        pay_choice = inquirer.confirm(message="예매 시 카드 결제", default=False)
    except Exception as e:
        print(e)
        print(colored("예매 정보 입력 중 취소되었습니다", "green", "on_red") + "\n")
        return

    options = {"type": type_choice, "pay": pay_choice}

    # Reserve function
    def _reserve(train):
        reserve = rail.reserve(train, passengers=passengers, option=options["type"])
        msg = f"{reserve}"
        if hasattr(reserve, "tickets") and reserve.tickets:
            msg += "\n" + "\n".join(map(str, reserve.tickets))

        print(colored(f"\n\n🎫 🎉 예매 성공!!! 🎉 🎫\n{msg}\n", "red", "on_green"))

        if options["pay"] and not reserve.is_waiting and pay_card(rail, reserve):
            print(
                colored("\n\n💳 ✨ 결제 성공!!! ✨ 💳\n\n", "green", "on_red"), end=""
            )
            msg += "\n결제 완료"

        tgprintf = get_telegram()
        asyncio.run(tgprintf(msg))

    # Reservation loop
    i_try = 0
    start_time = Time.time()
    while True:
        try:
            i_try += 1
            elapsed_time = Time.time() - start_time
            hours, remainder = divmod(int(elapsed_time), 3600)
            minutes, seconds = divmod(remainder, 60)
            print(
                f"\r예매 대기 중... {WAITING_BAR[i_try & 3]} {i_try:4d} ({hours:02d}:{minutes:02d}:{seconds:02d}) ",
                end="",
                flush=True,
            )

            trains = rail.search_train(**params)
            for i in selected_trains:
                if _is_seat_available(trains[i], options["type"], rail_type):
                    _reserve(trains[i])
                    return
            _sleep()

        except SRTError as ex:
            msg = ex.msg
            if "정상적인 경로로 접근 부탁드립니다" in msg or isinstance(
                ex, SRTNetFunnelError
            ):
                if debug:
                    print(
                        f"\nException: {ex}\nType: {type(ex)}\nArgs: {ex.args}\nMessage: {msg}"
                    )
                rail.clear()
            elif "로그인 후 사용하십시오" in msg:
                if debug:
                    print(
                        f"\nException: {ex}\nType: {type(ex)}\nArgs: {ex.args}\nMessage: {msg}"
                    )
                rail = login(rail_type, debug=debug)
                if not rail.is_login and not _handle_error(ex):
                    return
            elif not any(
                err in msg
                for err in (
                    "잔여석없음",
                    "사용자가 많아 접속이 원활하지 않습니다",
                    "예약대기 접수가 마감되었습니다",
                    "예약대기자한도수초과",
                )
            ):
                if not _handle_error(ex):
                    return
            _sleep()

        except KorailError as ex:
            msg = ex.msg
            if "Need to Login" in msg:
                rail = login(rail_type, debug=debug)
                if not rail.is_login and not _handle_error(ex):
                    return
            elif not any(
                err in msg
                for err in ("Sold out", "잔여석없음", "예약대기자한도수초과")
            ):
                if not _handle_error(ex):
                    return
            _sleep()

        except JSONDecodeError as ex:
            if debug:
                print(
                    f"\nException: {ex}\nType: {type(ex)}\nArgs: {ex.args}\nMessage: {ex.msg}"
                )
            _sleep()
            rail = login(rail_type, debug=debug)

        except ConnectionError as ex:
            if not _handle_error(ex, "연결이 끊겼습니다"):
                return
            rail = login(rail_type, debug=debug)

        except Exception as ex:
            if debug:
                print("\nUndefined exception")
            if not _handle_error(ex):
                return
            rail = login(rail_type, debug=debug)


def _sleep():
    Time.sleep(
        gammavariate(RESERVE_INTERVAL_SHAPE, RESERVE_INTERVAL_SCALE)
        + RESERVE_INTERVAL_MIN
    )


def _handle_error(ex, msg=None):
    msg = (
        msg
        or f"\nException: {ex}, Type: {type(ex)}, Message: {ex.msg if hasattr(ex, 'msg') else 'No message attribute'}"
    )
    print(msg)
    tgprintf = get_telegram()
    asyncio.run(tgprintf(msg))
    return inquirer.confirm(message="계속할까요", default=True).execute()


def _is_seat_available(train, seat_type, rail_type):
    if rail_type == "SRT":
        if not train.seat_available():
            return train.reserve_standby_available()
        if seat_type in [SeatType.GENERAL_FIRST, SeatType.SPECIAL_FIRST]:
            return train.seat_available()
        if seat_type == SeatType.GENERAL_ONLY:
            return train.general_seat_available()
        return train.special_seat_available()
    else:
        if not train.has_seat():
            return train.has_waiting_list()
        if seat_type in [ReserveOption.GENERAL_FIRST, ReserveOption.SPECIAL_FIRST]:
            return train.has_seat()
        if seat_type == ReserveOption.GENERAL_ONLY:
            return train.has_general_seat()
        return train.has_special_seat()


def check_reservation(rail_type="SRT", debug=False):
    rail = login(rail_type, debug=debug)

    while True:
        reservations = (
            rail.get_reservations() if rail_type == "SRT" else rail.reservations()
        )
        tickets = [] if rail_type == "SRT" else rail.tickets()

        all_reservations = []
        for t in tickets:
            t.is_ticket = True
            all_reservations.append(t)
        for r in reservations:
            if hasattr(r, "paid") and r.paid:
                r.is_ticket = True
            else:
                r.is_ticket = False
            all_reservations.append(r)

        if not reservations and not tickets:
            print(colored("예약 내역이 없습니다", "green", "on_red") + "\n")
            return

        choices = [
            (str(reservation), i) for i, reservation in enumerate(all_reservations)
        ] + [("텔레그램으로 예매 정보 전송", -2), ("돌아가기", -1)]

        try:
            choice = inquirer2.select(message="예약 취소 (Enter: 결정)", 
                                      choices=tuple_list_to_choice_list(choices), 
                                      keybindings=
                                        {
                                            "up": [{"key": "w"}],       # w로 위
                                            "down": [{"key": "s"}],     # s로 아래
                                            "answer": [{"key": "enter"}],
                                            "interrupt": [{"key": "c"}],
                                        },
                                      ).execute()
        except Exception:
            return

        # No choice or go back
        if choice in (None, -1):
            return

        # Send reservation info to telegram
        if choice == -2:
            out = []
            if all_reservations:
                out.append("[ 예매 내역 ]")
                for reservation in all_reservations:
                    out.append(f"🚅{reservation}")
                    if rail_type == "SRT":
                        out.extend(map(str, reservation.tickets))

            if out:
                tgprintf = get_telegram()
                asyncio.run(tgprintf("\n".join(out)))
            return

        # If choice is an unpaid reservation, ask to pay or cancel
        if (
            not all_reservations[choice].is_ticket
            and not all_reservations[choice].is_waiting
        ):
            try:
                answer = inquirer2.select(
                    message=f"결재 대기 승차권: {all_reservations[choice]}",
                    choices=tuple_list_to_choice_list([("결제하기", 1), ("취소하기", 2)]),
                    keybindings={
                        "up": [{"key": "w"}],       # w로 위
                        "down": [{"key": "s"}],     # s로 아래
                        "answer": [{"key": "enter"}],
                        "interrupt": [{"key": "c"}],
                    },
                ).execute()
            except Exception:
                return

            if answer == 1:
                if pay_card(rail, all_reservations[choice]):
                    print(
                        colored("\n\n💳 ✨ 결제 성공!!! ✨ 💳\n\n", "green", "on_red"),
                        end="",
                    )
            elif answer == 2:
                rail.cancel(all_reservations[choice])
            return

        # Else
        if inquirer.confirm(
            message="정말 취소하시겠습니까"
        ).execute():
            try:
                if all_reservations[choice].is_ticket:
                    rail.refund(all_reservations[choice])
                else:
                    rail.cancel(all_reservations[choice])
            except Exception as err:
                raise err
            return


if __name__ == "__main__":
    srtgo()
