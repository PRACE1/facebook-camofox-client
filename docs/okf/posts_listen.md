\# posts.listen action — behavior contract



\## purpose



`PostsListenAction` polls a Facebook group for new posts, persists a cursor across calls, and emits `posts.new` events only after durable commit.



\## public interface



\### input

`ActionEnvelope` with `input`:

```json

{

&#x20; "group\_id": "305056891435827",

&#x20; "terms": \[],

&#x20; "limit": 3

}

