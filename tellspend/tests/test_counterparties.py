import pytest

def create(client, headers, **fields):
    """Create a contact and return the response."""
    return client.post("/counterparties", json={"name": "Parth", **fields}, headers=headers)


# create
def test_create_cleans_input_and_defaults_to_person(client, make_user):
    headers = make_user()

    response = create(client, headers, name="  Parth   Shah ", relation="  My   Flatmate ")

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Parth Shah"
    assert body["counterparty_type"] == "PERSON"
    assert body["relation"] == "my flatmate"


def test_create_accepts_type_in_any_case(client, make_user):
    headers = make_user()

    assert create(client, headers, counterparty_type="business").json()["counterparty_type"] == "BUSINESS"


def test_create_stores_blank_relation_as_none(client, make_user):
    headers = make_user()

    assert create(client, headers, relation="   ").json()["relation"] is None


@pytest.mark.parametrize(
    "bad_fields",
    [
        {"name": ""},
        {"name": "   "},
        {"name": "x" * 256},
        {"counterparty_type": "FRIEND"},
        {"relation": "x" * 51},
    ],
)
def test_create_rejects_bad_input(client, make_user, bad_fields):
    headers = make_user()

    assert create(client, headers, **bad_fields).status_code == 422


def test_contacts_require_login(client):
    assert client.get("/counterparties").status_code == 401
    assert client.post("/counterparties", json={"name": "Parth"}).status_code == 401



# list and get
def test_list_is_alphabetical_ignoring_case_and_only_own(client, make_user):
    me = make_user("me@example.com")
    other = make_user("other@example.com")

    for name in ["riya", "Parth", "aman"]:
        create(client, me, name=name)
    create(client, other, name="Not mine")

    names = [c["name"] for c in client.get("/counterparties", headers=me).json()]

    assert names == ["aman", "Parth", "riya"]


def test_get_returns_own_contact_and_hides_others(client, make_user):
    me = make_user("me@example.com")
    other = make_user("other@example.com")
    mine = create(client, me).json()
    theirs = create(client, other).json()

    assert client.get(f"/counterparties/{mine['id']}", headers=me).status_code == 200
    assert client.get(f"/counterparties/{theirs['id']}", headers=me).status_code == 404
    assert client.get("/counterparties/999999", headers=me).status_code == 404



# update
def test_patch_rename_keeps_type_and_relation(client, make_user):
    headers = make_user()
    contact = create(client, headers, counterparty_type="BUSINESS", relation="landlord").json()

    response = client.patch(
        f"/counterparties/{contact['id']}",
        json={"name": "Swiggy India"},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Swiggy India"
    assert body["counterparty_type"] == "BUSINESS"
    assert body["relation"] == "landlord"


def test_patch_null_relation_clears_it(client, make_user):
    headers = make_user()
    contact = create(client, headers, relation="wife").json()

    response = client.patch(
        f"/counterparties/{contact['id']}",
        json={"relation": None},
        headers=headers,
    )

    assert response.json()["relation"] is None
    assert response.json()["name"] == "Parth"


def test_patch_changes_type(client, make_user):
    headers = make_user()
    contact = create(client, headers).json()

    response = client.patch(
        f"/counterparties/{contact['id']}",
        json={"counterparty_type": "organization"},
        headers=headers,
    )

    assert response.json()["counterparty_type"] == "ORGANIZATION"


@pytest.mark.parametrize(
    "bad_body",
    [
        {"name": None},
        {"name": "   "},
        {"counterparty_type": None},
        {"counterparty_type": "FRIEND"},
    ],
)
def test_patch_rejects_clearing_required_fields(client, make_user, bad_body):
    headers = make_user()
    contact = create(client, headers).json()

    response = client.patch(f"/counterparties/{contact['id']}", json=bad_body, headers=headers)

    assert response.status_code == 422


def test_patch_cannot_change_someone_elses_contact(client, make_user):
    me = make_user("me@example.com")
    other = make_user("other@example.com")
    theirs = create(client, other).json()

    response = client.patch(f"/counterparties/{theirs['id']}", json={"name": "Hacked"}, headers=me)

    assert response.status_code == 404
    assert client.get(f"/counterparties/{theirs['id']}", headers=other).json()["name"] == "Parth"


# delete
def test_delete_removes_contact(client, make_user):
    headers = make_user()
    contact = create(client, headers).json()

    assert client.delete(f"/counterparties/{contact['id']}", headers=headers).status_code == 204
    assert client.get(f"/counterparties/{contact['id']}", headers=headers).status_code == 404


def test_delete_cannot_remove_someone_elses_contact(client, make_user):
    me = make_user("me@example.com")
    other = make_user("other@example.com")
    theirs = create(client, other).json()

    assert client.delete(f"/counterparties/{theirs['id']}", headers=me).status_code == 404
    assert client.get(f"/counterparties/{theirs['id']}", headers=other).status_code == 200


def test_merging_two_names_for_one_person_moves_everything_and_keeps_balances_whole(client, make_user):
    headers = make_user()
    aadhya = client.post("/counterparties", json={"name": "Aadhya", "relation": "wife"}, headers=headers).json()["id"]
    typo = client.post("/counterparties", json={"name": "adhya"}, headers=headers).json()["id"]
    # One dinner with both names sharing, and a repayment under the typo.
    client.post("/expenses", headers=headers, json={
        "date": "2026-09-10", "amount": "900", "description": "Dinner",
        "items": [{"name": "Pizza", "amount": "900", "owners": [
            {"counterparty_id": aadhya, "amount": "300"}, {"counterparty_id": typo, "amount": "300"},
            {"counterparty_id": None, "amount": "300"}]}],
        "participants": [{"counterparty_id": None, "share_amount": "300"},
                         {"counterparty_id": aadhya, "share_amount": "300"},
                         {"counterparty_id": typo, "share_amount": "300"}]})
    client.post("/settlements", headers=headers, json={"counterparty_id": typo, "direction": "they_paid_me",
                                                       "amount": "200", "date": "2026-09-11"})

    merged = client.post(f"/counterparties/{aadhya}/merge", json={"into_id": typo}, headers=headers)

    assert merged.status_code == 200, merged.json()
    assert [c["name"] for c in client.get("/counterparties", headers=headers).json()] == ["Aadhya"]
    [expense] = client.get("/expenses", headers=headers).json()
    shares = {p["counterparty_id"]: p["share_amount"] for p in expense["participants"]}
    assert shares == {None: "300.00", aadhya: "600.00"}
    owners = {o["counterparty_id"]: o["amount"] for o in expense["items"][0]["owners"]}
    assert owners == {aadhya: "600.00", None: "300.00"}
    # She owed 600 (you paid), paid back 200: one balance, not two.
    balances = [(b["name"], b["amount"]) for b in client.get("/balances", headers=headers).json()]
    assert balances == [("Aadhya", "400.00")]


def test_a_contact_cant_be_merged_into_itself(client, make_user):
    headers = make_user()
    parth = client.post("/counterparties", json={"name": "Parth"}, headers=headers).json()["id"]

    assert client.post(f"/counterparties/{parth}/merge", json={"into_id": parth}, headers=headers).status_code == 422
