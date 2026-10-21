"""Write library/reading_lists/wide_net.json: a broad, popular reading list for sourcing.

Titles already in the catalog are dropped so the run only spends time on books the
vault does not have. Run with ``.venv/bin/python -m admin.build_wide_net_list``.
"""

from __future__ import annotations

import json
import re
import unicodedata

from app.config import settings

OUT = settings.BASE_DIR / "library" / "reading_lists" / "wide_net.json"
CATALOG = settings.BASE_DIR / "library" / "catalog.json"

LIST: dict[str, list[tuple[str, str]]] = {
    "Fantasy": [
        ("The Fellowship of the Ring", "J. R. R. Tolkien"), ("The Two Towers", "J. R. R. Tolkien"), ("The Return of the King", "J. R. R. Tolkien"),
        ("The Silmarillion", "J. R. R. Tolkien"), ("A Clash of Kings", "George R. R. Martin"), ("A Storm of Swords", "George R. R. Martin"),
        ("A Feast for Crows", "George R. R. Martin"), ("A Dance with Dragons", "George R. R. Martin"), ("Fire and Blood", "George R. R. Martin"),
        ("The Name of the Wind", "Patrick Rothfuss"), ("The Wise Man's Fear", "Patrick Rothfuss"), ("The Way of Kings", "Brandon Sanderson"),
        ("Words of Radiance", "Brandon Sanderson"), ("Mistborn: The Final Empire", "Brandon Sanderson"), ("The Well of Ascension", "Brandon Sanderson"),
        ("The Hero of Ages", "Brandon Sanderson"), ("Elantris", "Brandon Sanderson"), ("Warbreaker", "Brandon Sanderson"),
        ("The Eye of the World", "Robert Jordan"), ("The Great Hunt", "Robert Jordan"), ("Assassin's Apprentice", "Robin Hobb"),
        ("The Fifth Season", "N. K. Jemisin"), ("The Obelisk Gate", "N. K. Jemisin"), ("The Lies of Locke Lamora", "Scott Lynch"),
        ("The Blade Itself", "Joe Abercrombie"), ("Gardens of the Moon", "Steven Erikson"), ("The Black Company", "Glen Cook"),
        ("The Colour of Magic", "Terry Pratchett"), ("Mort", "Terry Pratchett"), ("Guards! Guards!", "Terry Pratchett"), ("Small Gods", "Terry Pratchett"),
        ("Good Omens", "Neil Gaiman"), ("American Gods", "Neil Gaiman"), ("Neverwhere", "Neil Gaiman"), ("Stardust", "Neil Gaiman"), ("Coraline", "Neil Gaiman"),
        ("The Ocean at the End of the Lane", "Neil Gaiman"), ("The Last Unicorn", "Peter S. Beagle"), ("The Princess Bride", "William Goldman"),
        ("A Wizard of Earthsea", "Ursula K. Le Guin"), ("The Tombs of Atuan", "Ursula K. Le Guin"), ("The Once and Future King", "T. H. White"),
        ("The Lion, the Witch and the Wardrobe", "C. S. Lewis"), ("Prince Caspian", "C. S. Lewis"), ("The Magician's Nephew", "C. S. Lewis"),
        ("The Golden Compass", "Philip Pullman"), ("The Subtle Knife", "Philip Pullman"), ("The Amber Spyglass", "Philip Pullman"),
        ("Eragon", "Christopher Paolini"), ("The Magicians", "Lev Grossman"), ("The Night Circus", "Erin Morgenstern"), ("Jonathan Strange & Mr Norrell", "Susanna Clarke"),
        ("Piranesi", "Susanna Clarke"), ("The Priory of the Orange Tree", "Samantha Shannon"), ("Six of Crows", "Leigh Bardugo"), ("Crooked Kingdom", "Leigh Bardugo"),
        ("Shadow and Bone", "Leigh Bardugo"), ("The Poppy War", "R. F. Kuang"), ("Babel", "R. F. Kuang"), ("Yellowface", "R. F. Kuang"),
        ("A Court of Thorns and Roses", "Sarah J. Maas"), ("A Court of Mist and Fury", "Sarah J. Maas"), ("Throne of Glass", "Sarah J. Maas"),
        ("Fourth Wing", "Rebecca Yarros"), ("Iron Flame", "Rebecca Yarros"), ("The Cruel Prince", "Holly Black"), ("Legends & Lattes", "Travis Baldree"),
        ("The House in the Cerulean Sea", "T. J. Klune"), ("Circe", "Madeline Miller"), ("The Song of Achilles", "Madeline Miller"),
        ("The Atlas Six", "Olivie Blake"), ("Howl's Moving Castle", "Diana Wynne Jones"), ("The Hobbit", "J. R. R. Tolkien"), ("A Game of Thrones", "George R. R. Martin"),
        ("Dune Messiah", "Frank Herbert"), ("Children of Dune", "Frank Herbert"), ("The Dragonbone Chair", "Tad Williams"), ("Red Rising", "Pierce Brown"), ("Golden Son", "Pierce Brown"),
    ],
    "Science fiction": [
        ("Dune", "Frank Herbert"), ("Foundation", "Isaac Asimov"), ("Foundation and Empire", "Isaac Asimov"), ("I, Robot", "Isaac Asimov"),
        ("Ender's Game", "Orson Scott Card"), ("Speaker for the Dead", "Orson Scott Card"), ("The Martian", "Andy Weir"), ("Project Hail Mary", "Andy Weir"),
        ("Artemis", "Andy Weir"), ("Neuromancer", "William Gibson"), ("Snow Crash", "Neal Stephenson"), ("Cryptonomicon", "Neal Stephenson"),
        ("Hyperion", "Dan Simmons"), ("The Left Hand of Darkness", "Ursula K. Le Guin"), ("The Dispossessed", "Ursula K. Le Guin"),
        ("Do Androids Dream of Electric Sheep?", "Philip K. Dick"), ("The Man in the High Castle", "Philip K. Dick"), ("Ubik", "Philip K. Dick"),
        ("Fahrenheit 451", "Ray Bradbury"), ("The Martian Chronicles", "Ray Bradbury"), ("Stranger in a Strange Land", "Robert A. Heinlein"),
        ("Starship Troopers", "Robert A. Heinlein"), ("The Hitchhiker's Guide to the Galaxy", "Douglas Adams"), ("The Restaurant at the End of the Universe", "Douglas Adams"),
        ("2001: A Space Odyssey", "Arthur C. Clarke"), ("Rendezvous with Rama", "Arthur C. Clarke"), ("Childhood's End", "Arthur C. Clarke"),
        ("The Three-Body Problem", "Liu Cixin"), ("The Dark Forest", "Liu Cixin"), ("Death's End", "Liu Cixin"), ("The Forever War", "Joe Haldeman"),
        ("Slaughterhouse-Five", "Kurt Vonnegut"), ("Cat's Cradle", "Kurt Vonnegut"), ("The Sirens of Titan", "Kurt Vonnegut"), ("Flowers for Algernon", "Daniel Keyes"),
        ("The Handmaid's Tale", "Margaret Atwood"), ("Oryx and Crake", "Margaret Atwood"), ("Never Let Me Go", "Kazuo Ishiguro"), ("Klara and the Sun", "Kazuo Ishiguro"),
        ("Station Eleven", "Emily St. John Mandel"), ("The Road", "Cormac McCarthy"), ("Blindsight", "Peter Watts"), ("Leviathan Wakes", "James S. A. Corey"),
        ("Old Man's War", "John Scalzi"), ("Ancillary Justice", "Ann Leckie"), ("A Fire Upon the Deep", "Vernor Vinge"), ("Ready Player One", "Ernest Cline"),
        ("The Time Machine", "H. G. Wells"), ("The War of the Worlds", "H. G. Wells"), ("Twenty Thousand Leagues Under the Sea", "Jules Verne"),
        ("Brave New World", "Aldous Huxley"), ("We", "Yevgeny Zamyatin"), ("A Canticle for Leibowitz", "Walter M. Miller Jr."), ("Solaris", "Stanisław Lem"),
        ("Exhalation", "Ted Chiang"), ("Stories of Your Life and Others", "Ted Chiang"), ("Recursion", "Blake Crouch"), ("Dark Matter", "Blake Crouch"),
        ("Children of Time", "Adrian Tchaikovsky"), ("Hail Mary", "Andy Weir"),
    ],
    "Romance and the BookTok shelf": [
        ("It Ends with Us", "Colleen Hoover"), ("It Starts with Us", "Colleen Hoover"), ("Verity", "Colleen Hoover"), ("Ugly Love", "Colleen Hoover"),
        ("Reminders of Him", "Colleen Hoover"), ("November 9", "Colleen Hoover"), ("Beach Read", "Emily Henry"), ("People We Meet on Vacation", "Emily Henry"),
        ("Book Lovers", "Emily Henry"), ("Happy Place", "Emily Henry"), ("Funny Story", "Emily Henry"), ("Normal People", "Sally Rooney"),
        ("Conversations with Friends", "Sally Rooney"), ("Beautiful World, Where Are You", "Sally Rooney"), ("The Seven Husbands of Evelyn Hugo", "Taylor Jenkins Reid"),
        ("Daisy Jones & The Six", "Taylor Jenkins Reid"), ("Malibu Rising", "Taylor Jenkins Reid"), ("Carrie Soto Is Back", "Taylor Jenkins Reid"),
        ("Outlander", "Diana Gabaldon"), ("Dragonfly in Amber", "Diana Gabaldon"), ("The Notebook", "Nicholas Sparks"), ("A Walk to Remember", "Nicholas Sparks"),
        ("Me Before You", "Jojo Moyes"), ("The Time Traveler's Wife", "Audrey Niffenegger"), ("The Fault in Our Stars", "John Green"), ("Looking for Alaska", "John Green"),
        ("Red, White & Royal Blue", "Casey McQuiston"), ("The Hating Game", "Sally Thorne"), ("The Kiss Quotient", "Helen Hoang"), ("The Love Hypothesis", "Ali Hazelwood"),
        ("Love and Other Words", "Christina Lauren"), ("The Unhoneymooners", "Christina Lauren"), ("Twisted Love", "Ana Huang"), ("Icebreaker", "Hannah Grace"),
        ("The Spanish Love Deception", "Elena Armas"), ("Things We Never Got Over", "Lucy Score"), ("Where the Crawdads Sing", "Delia Owens"),
        ("Eleanor Oliphant Is Completely Fine", "Gail Honeyman"), ("The Midnight Library", "Matt Haig"), ("Lessons in Chemistry", "Bonnie Garmus"),
        ("Tomorrow, and Tomorrow, and Tomorrow", "Gabrielle Zevin"), ("Little Fires Everywhere", "Celeste Ng"), ("Everything I Never Told You", "Celeste Ng"),
        ("Big Little Lies", "Liane Moriarty"), ("Nine Perfect Strangers", "Liane Moriarty"), ("The Nightingale", "Kristin Hannah"), ("The Four Winds", "Kristin Hannah"),
        ("The Great Alone", "Kristin Hannah"), ("The Women", "Kristin Hannah"), ("A Little Life", "Hanya Yanagihara"), ("The Secret History", "Donna Tartt"),
        ("The Goldfinch", "Donna Tartt"), ("My Year of Rest and Relaxation", "Ottessa Moshfegh"), ("Eileen", "Ottessa Moshfegh"), ("The Bell Jar", "Sylvia Plath"),
        ("Pride and Prejudice", "Jane Austen"), ("Emma", "Jane Austen"), ("Sense and Sensibility", "Jane Austen"), ("Persuasion", "Jane Austen"),
        ("Jane Eyre", "Charlotte Brontë"), ("Wuthering Heights", "Emily Brontë"), ("Rebecca", "Daphne du Maurier"), ("Little Women", "Louisa May Alcott"),
        ("Anne of Green Gables", "L. M. Montgomery"), ("The Color Purple", "Alice Walker"), ("Beloved", "Toni Morrison"), ("The Bluest Eye", "Toni Morrison"),
        ("Song of Solomon", "Toni Morrison"), ("The Joy Luck Club", "Amy Tan"), ("The House on Mango Street", "Sandra Cisneros"), ("Americanah", "Chimamanda Ngozi Adichie"),
        ("Half of a Yellow Sun", "Chimamanda Ngozi Adichie"), ("Pachinko", "Min Jin Lee"), ("Homegoing", "Yaa Gyasi"), ("The Vanishing Half", "Brit Bennett"),
        ("Such a Fun Age", "Kiley Reid"), ("Crying in H Mart", "Michelle Zauner"), ("Educated", "Tara Westover"), ("Becoming", "Michelle Obama"),
        ("Untamed", "Glennon Doyle"), ("Wild", "Cheryl Strayed"), ("Eat, Pray, Love", "Elizabeth Gilbert"), ("Big Magic", "Elizabeth Gilbert"),
        ("Women Who Run with the Wolves", "Clarissa Pinkola Estés"), ("The Handmaid's Tale", "Margaret Atwood"), ("Twilight", "Stephenie Meyer"), ("New Moon", "Stephenie Meyer"),
        ("Eclipse", "Stephenie Meyer"), ("Breaking Dawn", "Stephenie Meyer"), ("Midnight Sun", "Stephenie Meyer"), ("Fifty Shades of Grey", "E. L. James"),
    ],
    "Thrillers, mystery, horror": [
        ("Gone Girl", "Gillian Flynn"), ("Sharp Objects", "Gillian Flynn"), ("The Girl with the Dragon Tattoo", "Stieg Larsson"), ("The Girl on the Train", "Paula Hawkins"),
        ("The Da Vinci Code", "Dan Brown"), ("Angels & Demons", "Dan Brown"), ("The Silent Patient", "Alex Michaelides"), ("The Maidens", "Alex Michaelides"),
        ("And Then There Were None", "Agatha Christie"), ("Murder on the Orient Express", "Agatha Christie"), ("The Murder of Roger Ackroyd", "Agatha Christie"),
        ("The Hound of the Baskervilles", "Arthur Conan Doyle"), ("A Study in Scarlet", "Arthur Conan Doyle"), ("The Big Sleep", "Raymond Chandler"), ("The Maltese Falcon", "Dashiell Hammett"),
        ("In Cold Blood", "Truman Capote"), ("The Talented Mr. Ripley", "Patricia Highsmith"), ("Rebecca", "Daphne du Maurier"), ("The Silence of the Lambs", "Thomas Harris"),
        ("Red Dragon", "Thomas Harris"), ("The Shining", "Stephen King"), ("It", "Stephen King"), ("The Stand", "Stephen King"), ("Misery", "Stephen King"),
        ("Carrie", "Stephen King"), ("Pet Sematary", "Stephen King"), ("Salem's Lot", "Stephen King"), ("11/22/63", "Stephen King"), ("On Writing", "Stephen King"),
        ("The Green Mile", "Stephen King"), ("Dracula", "Bram Stoker"), ("Frankenstein", "Mary Shelley"), ("The Haunting of Hill House", "Shirley Jackson"),
        ("We Have Always Lived in the Castle", "Shirley Jackson"), ("The Exorcist", "William Peter Blatty"), ("Interview with the Vampire", "Anne Rice"), ("House of Leaves", "Mark Z. Danielewski"),
        ("Mexican Gothic", "Silvia Moreno-Garcia"), ("The Only Good Indians", "Stephen Graham Jones"), ("Bird Box", "Josh Malerman"), ("The Woman in the Window", "A. J. Finn"),
        ("Big Little Lies", "Liane Moriarty"), ("The Guest List", "Lucy Foley"), ("Verity", "Colleen Hoover"), ("The Thursday Murder Club", "Richard Osman"),
        ("The Lincoln Lawyer", "Michael Connelly"), ("The Firm", "John Grisham"), ("A Time to Kill", "John Grisham"), ("Jurassic Park", "Michael Crichton"),
        ("The Hunt for Red October", "Tom Clancy"), ("The Bourne Identity", "Robert Ludlum"), ("Shutter Island", "Dennis Lehane"), ("Mystic River", "Dennis Lehane"),
        ("The Name of the Rose", "Umberto Eco"), ("The Shadow of the Wind", "Carlos Ruiz Zafón"), ("Dark Places", "Gillian Flynn"), ("No Country for Old Men", "Cormac McCarthy"),
    ],
    "Young adult and childhood": [
        ("Harry Potter and the Chamber of Secrets", "J. K. Rowling"), ("Harry Potter and the Prisoner of Azkaban", "J. K. Rowling"), ("Harry Potter and the Goblet of Fire", "J. K. Rowling"),
        ("Harry Potter and the Order of the Phoenix", "J. K. Rowling"), ("Harry Potter and the Half-Blood Prince", "J. K. Rowling"), ("Harry Potter and the Deathly Hallows", "J. K. Rowling"),
        ("The Hunger Games", "Suzanne Collins"), ("Catching Fire", "Suzanne Collins"), ("Mockingjay", "Suzanne Collins"), ("The Ballad of Songbirds and Snakes", "Suzanne Collins"),
        ("Percy Jackson and the Lightning Thief", "Rick Riordan"), ("The Sea of Monsters", "Rick Riordan"), ("The Titan's Curse", "Rick Riordan"), ("Divergent", "Veronica Roth"),
        ("The Maze Runner", "James Dashner"), ("The Giver", "Lois Lowry"), ("Holes", "Louis Sachar"), ("Wonder", "R. J. Palacio"), ("The Perks of Being a Wallflower", "Stephen Chbosky"),
        ("Thirteen Reasons Why", "Jay Asher"), ("The Hate U Give", "Angie Thomas"), ("Speak", "Laurie Halse Anderson"), ("Eleanor & Park", "Rainbow Rowell"),
        ("The Book Thief", "Markus Zusak"), ("The Outsiders", "S. E. Hinton"), ("Where the Red Fern Grows", "Wilson Rawls"), ("Bridge to Terabithia", "Katherine Paterson"),
        ("Charlotte's Web", "E. B. White"), ("Matilda", "Roald Dahl"), ("Charlie and the Chocolate Factory", "Roald Dahl"), ("The BFG", "Roald Dahl"), ("James and the Giant Peach", "Roald Dahl"),
        ("A Wrinkle in Time", "Madeleine L'Engle"), ("The Phantom Tollbooth", "Norton Juster"), ("Hatchet", "Gary Paulsen"), ("Number the Stars", "Lois Lowry"),
        ("Diary of a Wimpy Kid", "Jeff Kinney"), ("Artemis Fowl", "Eoin Colfer"), ("The Mysterious Benedict Society", "Trenton Lee Stewart"), ("Inkheart", "Cornelia Funke"),
        ("The Graveyard Book", "Neil Gaiman"), ("Ender's Shadow", "Orson Scott Card"), ("Alice's Adventures in Wonderland", "Lewis Carroll"), ("The Wind in the Willows", "Kenneth Grahame"),
        ("Peter Pan", "J. M. Barrie"), ("The Secret Garden", "Frances Hodgson Burnett"), ("A Little Princess", "Frances Hodgson Burnett"), ("Treasure Island", "Robert Louis Stevenson"),
        ("The Call of the Wild", "Jack London"), ("White Fang", "Jack London"), ("Black Beauty", "Anna Sewell"), ("Heidi", "Johanna Spyri"), ("The Little Prince", "Antoine de Saint-Exupéry"),
        ("Winnie-the-Pooh", "A. A. Milne"), ("The Adventures of Tom Sawyer", "Mark Twain"), ("Adventures of Huckleberry Finn", "Mark Twain"), ("The Chronicles of Narnia", "C. S. Lewis"),
    ],
    "Classics and literary fiction": [
        ("The Great Gatsby", "F. Scott Fitzgerald"), ("Tender Is the Night", "F. Scott Fitzgerald"), ("To Kill a Mockingbird", "Harper Lee"), ("The Catcher in the Rye", "J. D. Salinger"),
        ("Of Mice and Men", "John Steinbeck"), ("The Grapes of Wrath", "John Steinbeck"), ("East of Eden", "John Steinbeck"), ("The Old Man and the Sea", "Ernest Hemingway"),
        ("A Farewell to Arms", "Ernest Hemingway"), ("The Sun Also Rises", "Ernest Hemingway"), ("For Whom the Bell Tolls", "Ernest Hemingway"), ("Moby-Dick", "Herman Melville"),
        ("The Scarlet Letter", "Nathaniel Hawthorne"), ("Great Expectations", "Charles Dickens"), ("A Tale of Two Cities", "Charles Dickens"), ("Oliver Twist", "Charles Dickens"),
        ("David Copperfield", "Charles Dickens"), ("A Christmas Carol", "Charles Dickens"), ("Bleak House", "Charles Dickens"), ("Middlemarch", "George Eliot"),
        ("Tess of the d'Urbervilles", "Thomas Hardy"), ("Far from the Madding Crowd", "Thomas Hardy"), ("Vanity Fair", "William Makepeace Thackeray"), ("Heart of Darkness", "Joseph Conrad"),
        ("Lord of the Flies", "William Golding"), ("Animal Farm", "George Orwell"), ("Nineteen Eighty-Four", "George Orwell"), ("Homage to Catalonia", "George Orwell"),
        ("Down and Out in Paris and London", "George Orwell"), ("Ulysses", "James Joyce"), ("Dubliners", "James Joyce"), ("A Portrait of the Artist as a Young Man", "James Joyce"),
        ("Mrs Dalloway", "Virginia Woolf"), ("To the Lighthouse", "Virginia Woolf"), ("A Room of One's Own", "Virginia Woolf"), ("Orlando", "Virginia Woolf"),
        ("The Picture of Dorian Gray", "Oscar Wilde"), ("The Importance of Being Earnest", "Oscar Wilde"), ("Dr Jekyll and Mr Hyde", "Robert Louis Stevenson"),
        ("War and Peace", "Leo Tolstoy"), ("Anna Karenina", "Leo Tolstoy"), ("The Death of Ivan Ilyich", "Leo Tolstoy"), ("Crime and Punishment", "Fyodor Dostoevsky"),
        ("The Brothers Karamazov", "Fyodor Dostoevsky"), ("Notes from Underground", "Fyodor Dostoevsky"), ("The Idiot", "Fyodor Dostoevsky"), ("Demons", "Fyodor Dostoevsky"),
        ("Dead Souls", "Nikolai Gogol"), ("Fathers and Sons", "Ivan Turgenev"), ("The Master and Margarita", "Mikhail Bulgakov"), ("Doctor Zhivago", "Boris Pasternak"),
        ("One Day in the Life of Ivan Denisovich", "Aleksandr Solzhenitsyn"), ("Lolita", "Vladimir Nabokov"), ("Pale Fire", "Vladimir Nabokov"), ("Madame Bovary", "Gustave Flaubert"),
        ("Les Misérables", "Victor Hugo"), ("The Hunchback of Notre-Dame", "Victor Hugo"), ("The Count of Monte Cristo", "Alexandre Dumas"), ("The Three Musketeers", "Alexandre Dumas"),
        ("The Stranger", "Albert Camus"), ("The Plague", "Albert Camus"), ("The Myth of Sisyphus", "Albert Camus"), ("The Fall", "Albert Camus"), ("Nausea", "Jean-Paul Sartre"),
        ("In Search of Lost Time: Swann's Way", "Marcel Proust"), ("Candide", "Voltaire"), ("Don Quixote", "Miguel de Cervantes"), ("The Divine Comedy", "Dante Alighieri"),
        ("The Decameron", "Giovanni Boccaccio"), ("Faust", "Johann Wolfgang von Goethe"), ("The Sorrows of Young Werther", "Johann Wolfgang von Goethe"), ("Steppenwolf", "Hermann Hesse"),
        ("Siddhartha", "Hermann Hesse"), ("Demian", "Hermann Hesse"), ("The Glass Bead Game", "Hermann Hesse"), ("The Trial", "Franz Kafka"), ("The Metamorphosis", "Franz Kafka"),
        ("The Castle", "Franz Kafka"), ("The Magic Mountain", "Thomas Mann"), ("Death in Venice", "Thomas Mann"), ("All Quiet on the Western Front", "Erich Maria Remarque"),
        ("The Tin Drum", "Günter Grass"), ("One Hundred Years of Solitude", "Gabriel García Márquez"), ("Love in the Time of Cholera", "Gabriel García Márquez"),
        ("Chronicle of a Death Foretold", "Gabriel García Márquez"), ("The House of the Spirits", "Isabel Allende"), ("Pedro Páramo", "Juan Rulfo"), ("Ficciones", "Jorge Luis Borges"),
        ("Labyrinths", "Jorge Luis Borges"), ("Hopscotch", "Julio Cortázar"), ("2666", "Roberto Bolaño"), ("The Savage Detectives", "Roberto Bolaño"), ("Blindness", "José Saramago"),
        ("The Unbearable Lightness of Being", "Milan Kundera"), ("Things Fall Apart", "Chinua Achebe"), ("Invisible Man", "Ralph Ellison"), ("Native Son", "Richard Wright"),
        ("Their Eyes Were Watching God", "Zora Neale Hurston"), ("Go Tell It on the Mountain", "James Baldwin"), ("Giovanni's Room", "James Baldwin"), ("The Fire Next Time", "James Baldwin"),
        ("Catch-22", "Joseph Heller"), ("One Flew Over the Cuckoo's Nest", "Ken Kesey"), ("On the Road", "Jack Kerouac"), ("Fear and Loathing in Las Vegas", "Hunter S. Thompson"),
        ("Infinite Jest", "David Foster Wallace"), ("Gravity's Rainbow", "Thomas Pynchon"), ("The Crying of Lot 49", "Thomas Pynchon"), ("White Noise", "Don DeLillo"),
        ("Underworld", "Don DeLillo"), ("Blood Meridian", "Cormac McCarthy"), ("All the Pretty Horses", "Cormac McCarthy"), ("Beloved", "Toni Morrison"), ("Housekeeping", "Marilynne Robinson"),
        ("Gilead", "Marilynne Robinson"), ("The Remains of the Day", "Kazuo Ishiguro"), ("Midnight's Children", "Salman Rushdie"), ("The God of Small Things", "Arundhati Roy"),
        ("Life of Pi", "Yann Martel"), ("The Kite Runner", "Khaled Hosseini"), ("A Thousand Splendid Suns", "Khaled Hosseini"), ("Norwegian Wood", "Haruki Murakami"),
        ("Kafka on the Shore", "Haruki Murakami"), ("The Wind-Up Bird Chronicle", "Haruki Murakami"), ("1Q84", "Haruki Murakami"), ("Snow Country", "Yasunari Kawabata"),
        ("Kokoro", "Natsume Sōseki"), ("No Longer Human", "Osamu Dazai"), ("The Tale of Genji", "Murasaki Shikibu"), ("Convenience Store Woman", "Sayaka Murata"),
        ("The Odyssey", "Homer"), ("The Iliad", "Homer"), ("The Aeneid", "Virgil"), ("Metamorphoses", "Ovid"), ("Beowulf", "Anonymous"), ("The Canterbury Tales", "Geoffrey Chaucer"),
        ("Hamlet", "William Shakespeare"), ("Macbeth", "William Shakespeare"), ("King Lear", "William Shakespeare"), ("Romeo and Juliet", "William Shakespeare"), ("Othello", "William Shakespeare"),
        ("The Tempest", "William Shakespeare"), ("A Midsummer Night's Dream", "William Shakespeare"), ("Paradise Lost", "John Milton"), ("Gulliver's Travels", "Jonathan Swift"),
        ("Robinson Crusoe", "Daniel Defoe"), ("Dracula", "Bram Stoker"), ("Leaves of Grass", "Walt Whitman"), ("The Waste Land", "T. S. Eliot"), ("Selected Poems", "Emily Dickinson"),
        ("The Collected Poems of Sylvia Plath", "Sylvia Plath"), ("Ariel", "Sylvia Plath"), ("Howl and Other Poems", "Allen Ginsberg"), ("The Essential Rumi", "Coleman Barks"),
        ("Milk and Honey", "Rupi Kaur"), ("The Sun and Her Flowers", "Rupi Kaur"), ("Devotions", "Mary Oliver"), ("The Prophet", "Kahlil Gibran"), ("Twenty Love Poems and a Song of Despair", "Pablo Neruda"),
    ],
    "Modern nonfiction and big ideas": [
        ("Sapiens", "Yuval Noah Harari"), ("Homo Deus", "Yuval Noah Harari"), ("21 Lessons for the 21st Century", "Yuval Noah Harari"), ("Thinking, Fast and Slow", "Daniel Kahneman"),
        ("Noise", "Daniel Kahneman"), ("Outliers", "Malcolm Gladwell"), ("The Tipping Point", "Malcolm Gladwell"), ("Blink", "Malcolm Gladwell"), ("Talking to Strangers", "Malcolm Gladwell"),
        ("Freakonomics", "Steven D. Levitt"), ("SuperFreakonomics", "Steven D. Levitt"), ("Guns, Germs, and Steel", "Jared Diamond"), ("Collapse", "Jared Diamond"),
        ("A Short History of Nearly Everything", "Bill Bryson"), ("The Body", "Bill Bryson"), ("Cosmos", "Carl Sagan"), ("Pale Blue Dot", "Carl Sagan"), ("The Demon-Haunted World", "Carl Sagan"),
        ("A Brief History of Time", "Stephen Hawking"), ("The Selfish Gene", "Richard Dawkins"), ("The Gene", "Siddhartha Mukherjee"), ("The Emperor of All Maladies", "Siddhartha Mukherjee"),
        ("The Immortal Life of Henrietta Lacks", "Rebecca Skloot"), ("Why We Sleep", "Matthew Walker"), ("Breath", "James Nestor"), ("The Body Keeps the Score", "Bessel van der Kolk"),
        ("Behave", "Robert Sapolsky"), ("Determined", "Robert Sapolsky"), ("The Power of Habit", "Charles Duhigg"), ("Atomic Habits", "James Clear"), ("Deep Work", "Cal Newport"),
        ("Digital Minimalism", "Cal Newport"), ("Essentialism", "Greg McKeown"), ("The 7 Habits of Highly Effective People", "Stephen R. Covey"), ("How to Win Friends and Influence People", "Dale Carnegie"),
        ("Man's Search for Meaning", "Viktor E. Frankl"), ("The Subtle Art of Not Giving a F*ck", "Mark Manson"), ("Can't Hurt Me", "David Goggins"), ("12 Rules for Life", "Jordan B. Peterson"),
        ("The Four Agreements", "Don Miguel Ruiz"), ("The Power of Now", "Eckhart Tolle"), ("A New Earth", "Eckhart Tolle"), ("The Alchemist", "Paulo Coelho"), ("The Untethered Soul", "Michael A. Singer"),
        ("Daring Greatly", "Brené Brown"), ("The Gifts of Imperfection", "Brené Brown"), ("Atlas of the Heart", "Brené Brown"), ("Quiet", "Susan Cain"), ("Grit", "Angela Duckworth"),
        ("Mindset", "Carol S. Dweck"), ("Flow", "Mihaly Csikszentmihalyi"), ("Drive", "Daniel H. Pink"), ("Range", "David Epstein"), ("Thinking in Systems", "Donella H. Meadows"),
        ("The Art of Thinking Clearly", "Rolf Dobelli"), ("Influence", "Robert B. Cialdini"), ("Predictably Irrational", "Dan Ariely"), ("Nudge", "Richard H. Thaler"), ("The Black Swan", "Nassim Nicholas Taleb"),
        ("Antifragile", "Nassim Nicholas Taleb"), ("Fooled by Randomness", "Nassim Nicholas Taleb"), ("Skin in the Game", "Nassim Nicholas Taleb"), ("The Psychology of Money", "Morgan Housel"),
        ("Rich Dad Poor Dad", "Robert T. Kiyosaki"), ("The Intelligent Investor", "Benjamin Graham"), ("The Millionaire Next Door", "Thomas J. Stanley"), ("I Will Teach You to Be Rich", "Ramit Sethi"),
        ("Zero to One", "Peter Thiel"), ("The Lean Startup", "Eric Ries"), ("The Hard Thing About Hard Things", "Ben Horowitz"), ("Shoe Dog", "Phil Knight"), ("Steve Jobs", "Walter Isaacson"),
        ("Elon Musk", "Walter Isaacson"), ("Leonardo da Vinci", "Walter Isaacson"), ("Einstein: His Life and Universe", "Walter Isaacson"), ("Good to Great", "Jim Collins"), ("Built to Last", "Jim Collins"),
        ("The Innovator's Dilemma", "Clayton M. Christensen"), ("Start with Why", "Simon Sinek"), ("Leaders Eat Last", "Simon Sinek"), ("Dare to Lead", "Brené Brown"), ("Radical Candor", "Kim Scott"),
        ("Never Split the Difference", "Chris Voss"), ("Getting to Yes", "Roger Fisher"), ("The 4-Hour Workweek", "Timothy Ferriss"), ("Tools of Titans", "Timothy Ferriss"), ("The Almanack of Naval Ravikant", "Eric Jorgenson"),
        ("The Creative Act", "Rick Rubin"), ("Steal Like an Artist", "Austin Kleon"), ("The War of Art", "Steven Pressfield"), ("Bird by Bird", "Anne Lamott"), ("The Artist's Way", "Julia Cameron"),
        ("Ways of Seeing", "John Berger"), ("The Story of Art", "E. H. Gombrich"), ("Just Kids", "Patti Smith"), ("Kitchen Confidential", "Anthony Bourdain"), ("Salt, Fat, Acid, Heat", "Samin Nosrat"),
        ("Into the Wild", "Jon Krakauer"), ("Into Thin Air", "Jon Krakauer"), ("Endurance", "Alfred Lansing"), ("Unbroken", "Laura Hillenbrand"), ("Born to Run", "Christopher McDougall"),
        ("When Breath Becomes Air", "Paul Kalanithi"), ("Being Mortal", "Atul Gawande"), ("The Checklist Manifesto", "Atul Gawande"), ("Tuesdays with Morrie", "Mitch Albom"), ("The Year of Magical Thinking", "Joan Didion"),
        ("Slouching Towards Bethlehem", "Joan Didion"), ("A Moveable Feast", "Ernest Hemingway"), ("Night", "Elie Wiesel"), ("The Diary of a Young Girl", "Anne Frank"), ("Maus", "Art Spiegelman"),
        ("Persepolis", "Marjane Satrapi"), ("Between the World and Me", "Ta-Nehisi Coates"), ("The New Jim Crow", "Michelle Alexander"), ("Caste", "Isabel Wilkerson"), ("The Warmth of Other Suns", "Isabel Wilkerson"),
        ("How to Be an Antiracist", "Ibram X. Kendi"), ("Stamped from the Beginning", "Ibram X. Kendi"), ("The Autobiography of Malcolm X", "Malcolm X"), ("I Know Why the Caged Bird Sings", "Maya Angelou"),
        ("Long Walk to Freedom", "Nelson Mandela"), ("Born a Crime", "Trevor Noah"), ("Greenlights", "Matthew McConaughey"), ("Open", "Andre Agassi"), ("Spare", "Prince Harry"),
        ("Bad Blood", "John Carreyrou"), ("The Big Short", "Michael Lewis"), ("Moneyball", "Michael Lewis"), ("Liar's Poker", "Michael Lewis"), ("Flash Boys", "Michael Lewis"),
        ("Evicted", "Matthew Desmond"), ("Nickel and Dimed", "Barbara Ehrenreich"), ("Hillbilly Elegy", "J. D. Vance"), ("Say Nothing", "Patrick Radden Keefe"), ("Empire of Pain", "Patrick Radden Keefe"),
        ("Killers of the Flower Moon", "David Grann"), ("The Wager", "David Grann"), ("The Devil in the White City", "Erik Larson"), ("The Splendid and the Vile", "Erik Larson"),
        ("1776", "David McCullough"), ("John Adams", "David McCullough"), ("Team of Rivals", "Doris Kearns Goodwin"), ("Alexander Hamilton", "Ron Chernow"), ("Titan", "Ron Chernow"),
        ("SPQR", "Mary Beard"), ("The Rise and Fall of the Third Reich", "William L. Shirer"), ("A People's History of the United States", "Howard Zinn"), ("The Guns of August", "Barbara W. Tuchman"),
        ("The Silk Roads", "Peter Frankopan"), ("Prisoners of Geography", "Tim Marshall"), ("The Origins of Totalitarianism", "Hannah Arendt"), ("Eichmann in Jerusalem", "Hannah Arendt"),
        ("Orientalism", "Edward W. Said"), ("Discipline and Punish", "Michel Foucault"), ("Simulacra and Simulation", "Jean Baudrillard"), ("The Society of the Spectacle", "Guy Debord"),
        ("Manufacturing Consent", "Noam Chomsky"), ("Capital in the Twenty-First Century", "Thomas Piketty"), ("Debt: The First 5,000 Years", "David Graeber"), ("Bullshit Jobs", "David Graeber"),
        ("The Dawn of Everything", "David Graeber"), ("Amusing Ourselves to Death", "Neil Postman"), ("The Shallows", "Nicholas Carr"), ("Stolen Focus", "Johann Hari"), ("Lost Connections", "Johann Hari"),
        ("Dopamine Nation", "Anna Lembke"), ("The Anxious Generation", "Jonathan Haidt"), ("The Righteous Mind", "Jonathan Haidt"), ("The Coddling of the American Mind", "Jonathan Haidt"),
        ("Gödel, Escher, Bach", "Douglas Hofstadter"), ("The Structure of Scientific Revolutions", "Thomas S. Kuhn"), ("The Elegant Universe", "Brian Greene"), ("Seven Brief Lessons on Physics", "Carlo Rovelli"),
        ("The Order of Time", "Carlo Rovelli"), ("What If?", "Randall Munroe"), ("Astrophysics for People in a Hurry", "Neil deGrasse Tyson"), ("The Sixth Extinction", "Elizabeth Kolbert"),
        ("Silent Spring", "Rachel Carson"), ("Braiding Sweetgrass", "Robin Wall Kimmerer"), ("The Hidden Life of Trees", "Peter Wohlleben"), ("Entangled Life", "Merlin Sheldrake"),
        ("Superintelligence", "Nick Bostrom"), ("Life 3.0", "Max Tegmark"), ("The Alignment Problem", "Brian Christian"), ("Algorithms to Live By", "Brian Christian"), ("The Code Breaker", "Walter Isaacson"),
        ("The Art of War", "Sun Tzu"), ("The Prince", "Niccolò Machiavelli"), ("Meditations", "Marcus Aurelius"), ("Letters from a Stoic", "Seneca"), ("The Enchiridion", "Epictetus"),
        ("The Daily Stoic", "Ryan Holiday"), ("The Obstacle Is the Way", "Ryan Holiday"), ("Ego Is the Enemy", "Ryan Holiday"), ("Stillness Is the Key", "Ryan Holiday"), ("Mastery", "Robert Greene"),
        ("The Laws of Human Nature", "Robert Greene"), ("The Art of Seduction", "Robert Greene"), ("The 33 Strategies of War", "Robert Greene"), ("The 48 Laws of Power", "Robert Greene"),
        ("Models", "Mark Manson"), ("The Mountain Is You", "Brianna Wiest"), ("101 Essays That Will Change the Way You Think", "Brianna Wiest"), ("Attached", "Amir Levine"), ("The Five Love Languages", "Gary Chapman"),
        ("Come as You Are", "Emily Nagoski"), ("Burnout", "Emily Nagoski"), ("Why Does He Do That?", "Lundy Bancroft"), ("Adult Children of Emotionally Immature Parents", "Lindsay C. Gibson"),
        ("The Courage to Be Disliked", "Ichiro Kishimi"), ("Ikigai", "Héctor García"), ("The Life-Changing Magic of Tidying Up", "Marie Kondo"), ("Wabi Sabi", "Beth Kempton"),
        ("Zen and the Art of Motorcycle Maintenance", "Robert M. Pirsig"), ("The Tao of Pooh", "Benjamin Hoff"), ("Tao Te Ching", "Lao Tzu"), ("The Bhagavad Gita", "Anonymous"), ("The Dhammapada", "Anonymous"),
        ("Zen Mind, Beginner's Mind", "Shunryu Suzuki"), ("The Miracle of Mindfulness", "Thich Nhat Hanh"), ("Peace Is Every Step", "Thich Nhat Hanh"), ("Wherever You Go, There You Are", "Jon Kabat-Zinn"),
        ("Mere Christianity", "C. S. Lewis"), ("The Screwtape Letters", "C. S. Lewis"), ("Confessions", "Augustine of Hippo"), ("The Imitation of Christ", "Thomas à Kempis"), ("The Varieties of Religious Experience", "William James"),
    ],
    "Manga and graphic novels": [
        ("Berserk", "Kentaro Miura"), ("One Piece", "Eiichiro Oda"), ("Naruto", "Masashi Kishimoto"), ("Death Note", "Tsugumi Ohba"), ("Attack on Titan", "Hajime Isayama"),
        ("Fullmetal Alchemist", "Hiromu Arakawa"), ("Dragon Ball", "Akira Toriyama"), ("Vagabond", "Takehiko Inoue"), ("Slam Dunk", "Takehiko Inoue"), ("Monster", "Naoki Urasawa"),
        ("20th Century Boys", "Naoki Urasawa"), ("Akira", "Katsuhiro Otomo"), ("Ghost in the Shell", "Masamune Shirow"), ("Chainsaw Man", "Tatsuki Fujimoto"), ("Jujutsu Kaisen", "Gege Akutami"),
        ("Demon Slayer", "Koyoharu Gotouge"), ("My Hero Academia", "Kohei Horikoshi"), ("Hunter x Hunter", "Yoshihiro Togashi"), ("Bleach", "Tite Kubo"), ("Tokyo Ghoul", "Sui Ishida"),
        ("Vinland Saga", "Makoto Yukimura"), ("Oyasumi Punpun", "Inio Asano"), ("Nausicaä of the Valley of the Wind", "Hayao Miyazaki"), ("Sailor Moon", "Naoko Takeuchi"), ("Fruits Basket", "Natsuki Takaya"),
        ("Watchmen", "Alan Moore"), ("V for Vendetta", "Alan Moore"), ("The Sandman", "Neil Gaiman"), ("Batman: The Dark Knight Returns", "Frank Miller"), ("Batman: Year One", "Frank Miller"),
        ("Saga", "Brian K. Vaughan"), ("Y: The Last Man", "Brian K. Vaughan"), ("Fun Home", "Alison Bechdel"), ("Blankets", "Craig Thompson"), ("Understanding Comics", "Scott McCloud"),
    ],
}


def normalize(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    ascii_value = re.sub(r"^(the|a|an)\s+", "", ascii_value.casefold().strip())
    return re.sub(r"[^a-z0-9]+", " ", ascii_value).strip()


def main() -> None:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))["books"]
    have = {normalize(book.get("title") or "") for book in catalog}
    books: list[dict] = []
    seen: set[str] = set()
    skipped: list[str] = []
    for category, items in LIST.items():
        for title, author in items:
            key = normalize(title)
            if key in seen:
                continue
            seen.add(key)
            if key in have:
                skipped.append(title)
                continue
            books.append({"category": category, "title": title, "author": author})
    payload = {
        "name": "Wide net",
        "description": "Popular books across genres that the vault does not have yet, for the review room.",
        "batch_size": 40,
        "books": books,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(books)} titles to source · {len(skipped)} already in the vault")
    print("already there:", ", ".join(sorted(skipped)[:40]), "…" if len(skipped) > 40 else "")


if __name__ == "__main__":
    main()
