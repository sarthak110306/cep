-- ============================================================
-- Community Hackathon Database Schema for PostgreSQL / Supabase
-- ============================================================

-- 1. USERS
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(150) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. ADMINS
CREATE TABLE IF NOT EXISTS admins (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(150) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. PROBLEM STATEMENTS
CREATE TABLE IF NOT EXISTS problem_statements (
    id SERIAL PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    category VARCHAR(50) NOT NULL,
    description TEXT NOT NULL,
    difficulty VARCHAR(20) DEFAULT 'Medium',
    technologies TEXT,
    social_impact TEXT,
    icon VARCHAR(10) DEFAULT '🎯',
    example_text TEXT,
    solution_text TEXT,
    importance_text TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. USER PROBLEM SELECTIONS
CREATE TABLE IF NOT EXISTS user_problem_selections (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    problem_statement_id INT NOT NULL REFERENCES problem_statements(id) ON DELETE CASCADE,
    selected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_user_selection UNIQUE (user_id)
);

-- 5. TEAMS
CREATE TABLE IF NOT EXISTS teams (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    team_name VARCHAR(150) NOT NULL,
    team_leader VARCHAR(100) NOT NULL,
    college VARCHAR(200) NOT NULL,
    email VARCHAR(150) NOT NULL,
    phone VARCHAR(20) NOT NULL,
    problem_statement_id INT NOT NULL REFERENCES problem_statements(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_user_team UNIQUE (user_id),
    CONSTRAINT unique_team_name UNIQUE (team_name)
);

-- 6. TEAM MEMBERS
CREATE TABLE IF NOT EXISTS team_members (
    id SERIAL PRIMARY KEY,
    team_id INT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    member_name VARCHAR(100) NOT NULL
);

-- 7. REGISTRATIONS
CREATE TABLE IF NOT EXISTS registrations (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    team_id INT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    registration_id VARCHAR(20) UNIQUE,
    status VARCHAR(20) DEFAULT 'Draft',
    confirmed_at TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_user_registration UNIQUE (user_id)
);

-- 8. JUDGES & MENTORS
CREATE TABLE IF NOT EXISTS judges_mentors (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    role VARCHAR(100),
    organization VARCHAR(150),
    expertise VARCHAR(255),
    experience VARCHAR(50),
    bio TEXT,
    image VARCHAR(500),
    type VARCHAR(20) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 9. EVENTS / SCHEDULE
CREATE TABLE IF NOT EXISTS events (
    id SERIAL PRIMARY KEY,
    event_name VARCHAR(200) NOT NULL,
    event_date DATE NOT NULL,
    event_time TIME NOT NULL,
    venue VARCHAR(200),
    description TEXT,
    category VARCHAR(50),
    duration VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 10. FAQS
CREATE TABLE IF NOT EXISTS faqs (
    id SERIAL PRIMARY KEY,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    category VARCHAR(50) DEFAULT 'General',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 11. CONTACT MESSAGES
CREATE TABLE IF NOT EXISTS contact_messages (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(150) NOT NULL,
    subject VARCHAR(200) NOT NULL,
    message TEXT NOT NULL,
    is_read SMALLINT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 12. USER JUDGE SELECTIONS
CREATE TABLE IF NOT EXISTS user_judge_selections (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    judge_mentor_id INT NOT NULL REFERENCES judges_mentors(id) ON DELETE CASCADE,
    selected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 13. USER EVENT SELECTIONS
CREATE TABLE IF NOT EXISTS user_event_selections (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    event_id INT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    selected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 14. USER FAQ SELECTIONS
CREATE TABLE IF NOT EXISTS user_faq_selections (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    faq_id INT NOT NULL REFERENCES faqs(id) ON DELETE CASCADE,
    selected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 15. USER FAQ MESSAGES
CREATE TABLE IF NOT EXISTS user_faq_messages (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(100),
    email VARCHAR(150),
    message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 16. CERTIFICATES
CREATE TABLE IF NOT EXISTS certificates (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    certificate_id VARCHAR(50) UNIQUE NOT NULL,
    certificate_type VARCHAR(50) NOT NULL,
    position VARCHAR(50),
    team_name VARCHAR(150),
    problem_statement VARCHAR(200),
    issued_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- SEED DATA
-- ============================================================

-- Problem Statements
INSERT INTO problem_statements
(title, category, description, difficulty, technologies, social_impact, icon, example_text, solution_text, importance_text)
SELECT 'Rural Learning Access', 'Education',
 'Design a platform that provides quality educational content to students in remote areas with limited internet access.',
 'Medium', 'Progressive Web App, SQLite, Service Workers, Android',
 'Bridges the education gap between rural and urban students, improving literacy and long-term opportunity.',
 '🎓',
 'Villages with intermittent connectivity often cannot access online classes, leaving students behind their urban peers.',
 'A lightweight app that caches lessons offline and syncs progress automatically once connectivity is available.',
 'Access to quality education directly shapes future opportunities, and closing this gap helps break the cycle of inequality in remote communities.'
WHERE NOT EXISTS (SELECT 1 FROM problem_statements WHERE title = 'Rural Learning Access');

INSERT INTO problem_statements
(title, category, description, difficulty, technologies, social_impact, icon, example_text, solution_text, importance_text)
SELECT 'Affordable Telemedicine', 'Healthcare',
 'Build a solution that connects underserved communities with certified doctors through low-bandwidth video or chat consultations.',
 'Hard', 'Flask/Node backend, WebRTC, Machine Learning, Twilio API',
 'Reduces travel burden and enables timely medical care for underserved populations.',
 '🏥',
 'Many rural clinics lack specialist doctors, forcing patients to travel hours for basic consultations.',
 'A low-bandwidth consultation app with AI-based symptom triage to prioritize urgent cases before doctor review.',
 'Timely access to healthcare can be the difference between life and death — this solution brings specialists within reach of anyone with a phone.'
WHERE NOT EXISTS (SELECT 1 FROM problem_statements WHERE title = 'Affordable Telemedicine');

INSERT INTO problem_statements
(title, category, description, difficulty, technologies, social_impact, icon, example_text, solution_text, importance_text)
SELECT 'Smart Waste Management', 'Environment',
 'Create a system to track, report, and optimize waste collection routes to reduce pollution and improve recycling rates.',
 'Medium', 'IoT Sensors, Google Maps API, React Dashboard',
 'Cleaner cities, lower emissions from collection vehicles, and improved recycling participation.',
 '🌱',
 'Overflowing bins and inefficient collection routes lead to littering and higher fuel costs for municipalities.',
 'IoT-enabled bins that report fill levels in real time, paired with a route optimization dashboard for collection trucks.',
 'Efficient waste management reduces environmental damage and public health risks while saving civic resources.'
WHERE NOT EXISTS (SELECT 1 FROM problem_statements WHERE title = 'Smart Waste Management');

INSERT INTO problem_statements
(title, category, description, difficulty, technologies, social_impact, icon, example_text, solution_text, importance_text)
SELECT 'Smart Crop Advisory', 'Agriculture',
 'Develop a tool that gives farmers real-time crop health insights, weather alerts, and market price predictions.',
 'Medium', 'Python, TensorFlow, Weather API, React Native',
 'Increases crop yield, reduces losses, and improves farmer income stability.',
 '🌾',
 'Farmers often lose crops due to unexpected weather changes or sell produce at unfair prices due to lack of market data.',
 'A mobile app combining weather forecasts, soil data, and live market price trends to guide farming decisions.',
 'Agriculture supports millions of livelihoods — smarter decisions directly improve food security and farmer welfare.'
WHERE NOT EXISTS (SELECT 1 FROM problem_statements WHERE title = 'Smart Crop Advisory');

INSERT INTO problem_statements
(title, category, description, difficulty, technologies, social_impact, icon, example_text, solution_text, importance_text)
SELECT 'Intelligent Traffic Management', 'Smart City',
 'Build a system that analyzes real-time traffic data to optimize signal timing and reduce urban congestion.',
 'Hard', 'OpenCV, Python, IoT Controllers, Cloud Analytics',
 'Reduces commute times, fuel consumption, and traffic-related emissions city-wide.',
 '🏙️',
 'Fixed-timing traffic signals cause unnecessary congestion during off-peak hours and accidents during rush hours.',
 'Camera-based vehicle density detection feeding into an adaptive signal control system that adjusts in real time.',
 'Smarter traffic systems save commuters time daily and significantly cut down urban air pollution.'
WHERE NOT EXISTS (SELECT 1 FROM problem_statements WHERE title = 'Intelligent Traffic Management');

INSERT INTO problem_statements
(title, category, description, difficulty, technologies, social_impact, icon, example_text, solution_text, importance_text)
SELECT 'Emergency Safety Companion', 'Women Safety',
 'Create a personal safety app with one-tap SOS alerts, live location sharing, and community-verified safe routes.',
 'Medium', 'React Native, Firebase, Google Maps API, Push Notifications',
 'Provides faster emergency response and greater confidence and safety for women in public spaces.',
 '🛡️',
 'Women commuting alone at night often lack a quick, reliable way to alert trusted contacts in emergencies.',
 'A mobile app with a one-tap SOS button, live GPS tracking, and crowd-sourced safe-route recommendations.',
 'Personal safety technology empowers women to move freely and confidently, addressing a critical everyday concern.'
WHERE NOT EXISTS (SELECT 1 FROM problem_statements WHERE title = 'Emergency Safety Companion');

-- Judges & Mentors
INSERT INTO judges_mentors (name, role, organization, expertise, experience, bio, image, type)
SELECT 'Ananya Sharma', 'Senior AI Research Lead', 'Microsoft', 'AI, Machine Learning', '12+ Years',
 'Ananya leads applied AI research and has judged over 40 hackathons, focused on evaluating real-world impact and technical depth.',
 'https://i.pravatar.cc/300?img=32', 'Judge'
WHERE NOT EXISTS (SELECT 1 FROM judges_mentors WHERE name = 'Ananya Sharma');

INSERT INTO judges_mentors (name, role, organization, expertise, experience, bio, image, type)
SELECT 'Rohan Verma', 'Principal Cloud Architect', 'Amazon Web Services', 'Cloud Computing, DevOps', '14+ Years',
 'Rohan specializes in scalable cloud infrastructure and has mentored dozens of student startups on architecture best practices.',
 'https://i.pravatar.cc/300?img=13', 'Judge'
WHERE NOT EXISTS (SELECT 1 FROM judges_mentors WHERE name = 'Rohan Verma');

INSERT INTO judges_mentors (name, role, organization, expertise, experience, bio, image, type)
SELECT 'Priya Nair', 'Director of Engineering', 'Google', 'Web Development, AI', '16+ Years',
 'Priya has led multiple engineering teams building large-scale consumer products and loves discovering socially impactful ideas.',
 'https://i.pravatar.cc/300?img=47', 'Judge'
WHERE NOT EXISTS (SELECT 1 FROM judges_mentors WHERE name = 'Priya Nair');

INSERT INTO judges_mentors (name, role, organization, expertise, experience, bio, image, type)
SELECT 'Karan Mehta', 'Cyber Security Lead', 'IBM', 'Cyber Security, Cloud Computing', '11+ Years',
 'Karan focuses on secure system design and has helped organizations build resilient, privacy-first products.',
 'https://i.pravatar.cc/300?img=51', 'Judge'
WHERE NOT EXISTS (SELECT 1 FROM judges_mentors WHERE name = 'Karan Mehta');

INSERT INTO judges_mentors (name, role, organization, expertise, experience, bio, image, type)
SELECT 'Sneha Kapoor', 'Head of Product Design', 'Adobe', 'UI/UX, Web Development', '10+ Years',
 'Sneha champions design thinking and has mentored teams to turn raw ideas into polished, user-centered products.',
 'https://i.pravatar.cc/300?img=45', 'Judge'
WHERE NOT EXISTS (SELECT 1 FROM judges_mentors WHERE name = 'Sneha Kapoor');

INSERT INTO judges_mentors (name, role, organization, expertise, experience, bio, image, type)
SELECT 'Arjun Reddy', 'VP of Engineering', 'Flipkart', 'AI, Web Development', '15+ Years',
 'Arjun has scaled engineering teams from the ground up and values pragmatic, high-impact solutions above all else.',
 'https://i.pravatar.cc/300?img=14', 'Judge'
WHERE NOT EXISTS (SELECT 1 FROM judges_mentors WHERE name = 'Arjun Reddy');

INSERT INTO judges_mentors (name, role, organization, expertise, experience, bio, image, type)
SELECT 'Neha Joshi', 'Senior Software Engineer', 'Salesforce', 'Web Development, Cloud Computing', '8+ Years',
 'Neha enjoys helping student teams debug tricky architecture decisions and ship working prototypes fast.',
 'https://i.pravatar.cc/300?img=26', 'Mentor'
WHERE NOT EXISTS (SELECT 1 FROM judges_mentors WHERE name = 'Neha Joshi');

INSERT INTO judges_mentors (name, role, organization, expertise, experience, bio, image, type)
SELECT 'Aditya Rao', 'Machine Learning Engineer', 'NVIDIA', 'AI, Cloud Computing', '7+ Years',
 'Aditya specializes in applied ML and loves guiding teams through model selection and deployment challenges.',
 'https://i.pravatar.cc/300?img=15', 'Mentor'
WHERE NOT EXISTS (SELECT 1 FROM judges_mentors WHERE name = 'Aditya Rao');

INSERT INTO judges_mentors (name, role, organization, expertise, experience, bio, image, type)
SELECT 'Ishita Bose', 'UX Designer', 'Zoho', 'UI/UX', '6+ Years',
 'Ishita helps teams craft intuitive interfaces and validate designs quickly with simple usability principles.',
 'https://i.pravatar.cc/300?img=48', 'Mentor'
WHERE NOT EXISTS (SELECT 1 FROM judges_mentors WHERE name = 'Ishita Bose');

INSERT INTO judges_mentors (name, role, organization, expertise, experience, bio, image, type)
SELECT 'Varun Malhotra', 'Security Consultant', 'Deloitte', 'Cyber Security', '9+ Years',
 'Varun guides teams on secure coding practices and helps identify vulnerabilities before demo day.',
 'https://i.pravatar.cc/300?img=11', 'Mentor'
WHERE NOT EXISTS (SELECT 1 FROM judges_mentors WHERE name = 'Varun Malhotra');

INSERT INTO judges_mentors (name, role, organization, expertise, experience, bio, image, type)
SELECT 'Meera Iyer', 'Full Stack Developer', 'Freshworks', 'Web Development', '6+ Years',
 'Meera loves pairing with student teams to unblock tricky bugs and ship polished full-stack applications.',
 'https://i.pravatar.cc/300?img=44', 'Mentor'
WHERE NOT EXISTS (SELECT 1 FROM judges_mentors WHERE name = 'Meera Iyer');

INSERT INTO judges_mentors (name, role, organization, expertise, experience, bio, image, type)
SELECT 'Siddharth Nair', 'DevOps Engineer', 'Infosys', 'Cloud Computing, Cyber Security', '8+ Years',
 'Siddharth helps teams set up reliable deployment pipelines and understand cloud cost and security trade-offs.',
 'https://i.pravatar.cc/300?img=33', 'Mentor'
WHERE NOT EXISTS (SELECT 1 FROM judges_mentors WHERE name = 'Siddharth Nair');

-- Events / Schedule
INSERT INTO events (event_name, event_date, event_time, venue, description, category, duration)
SELECT 'Registration & Check-in', '2026-08-15', '09:00:00', 'College Auditorium Lobby',
 'Participants check in, collect ID badges and kits, and settle into their assigned team zones.', 'Registration', '1 hour'
WHERE NOT EXISTS (SELECT 1 FROM events WHERE event_name = 'Registration & Check-in');

INSERT INTO events (event_name, event_date, event_time, venue, description, category, duration)
SELECT 'Opening Ceremony', '2026-08-15', '10:00:00', 'Main Auditorium Stage',
 'Welcome address, introduction of judges and mentors, and an overview of the hackathon theme and rules.', 'Ceremony', '1 hour'
WHERE NOT EXISTS (SELECT 1 FROM events WHERE event_name = 'Opening Ceremony');

INSERT INTO events (event_name, event_date, event_time, venue, description, category, duration)
SELECT 'Hackathon Begins', '2026-08-15', '11:00:00', 'Team Work Zones',
 'The 24-hour coding challenge officially kicks off. Teams begin ideating and building their solutions.', 'Hackathon', '2 hours'
WHERE NOT EXISTS (SELECT 1 FROM events WHERE event_name = 'Hackathon Begins');

INSERT INTO events (event_name, event_date, event_time, venue, description, category, duration)
SELECT 'Mentor Session', '2026-08-15', '13:00:00', 'Mentor Lounge & Team Zones',
 'Teams get one-on-one guidance from industry mentors to refine their approach and technical direction.', 'Mentoring', '1 hour'
WHERE NOT EXISTS (SELECT 1 FROM events WHERE event_name = 'Mentor Session');

INSERT INTO events (event_name, event_date, event_time, venue, description, category, duration)
SELECT 'Innovation Workshop', '2026-08-15', '16:00:00', 'Workshop Hall',
 'A hands-on session covering rapid prototyping, pitching techniques, and effective use of APIs.', 'Workshop', '1 hour'
WHERE NOT EXISTS (SELECT 1 FROM events WHERE event_name = 'Innovation Workshop');

INSERT INTO events (event_name, event_date, event_time, venue, description, category, duration)
SELECT 'Progress Review', '2026-08-15', '18:00:00', 'Team Work Zones',
 'Judges and mentors walk around to check progress and offer quick feedback on each team build.', 'Review', '1 hour'
WHERE NOT EXISTS (SELECT 1 FROM events WHERE event_name = 'Progress Review');

INSERT INTO events (event_name, event_date, event_time, venue, description, category, duration)
SELECT 'Dinner & Networking', '2026-08-15', '21:00:00', 'Cafeteria',
 'A relaxed dinner break where participants can network with mentors, judges, and fellow teams.', 'Break', '1 hour'
WHERE NOT EXISTS (SELECT 1 FROM events WHERE event_name = 'Dinner & Networking');

INSERT INTO events (event_name, event_date, event_time, venue, description, category, duration)
SELECT 'Midnight Challenge', '2026-08-16', '00:00:00', 'Main Auditorium',
 'A fun surprise mini-challenge to keep energy high through the night, with small prizes for winners.', 'Hackathon', '1 hour'
WHERE NOT EXISTS (SELECT 1 FROM events WHERE event_name = 'Midnight Challenge');

INSERT INTO events (event_name, event_date, event_time, venue, description, category, duration)
SELECT 'Final Development Sprint', '2026-08-16', '06:00:00', 'Team Work Zones',
 'The last stretch of development time before submissions close. Teams finalize and polish their projects.', 'Hackathon', '3 hours'
WHERE NOT EXISTS (SELECT 1 FROM events WHERE event_name = 'Final Development Sprint');

INSERT INTO events (event_name, event_date, event_time, venue, description, category, duration)
SELECT 'Project Submission', '2026-08-16', '09:00:00', 'Online Submission Portal',
 'All teams submit their final project, source code, and presentation deck through the portal.', 'Hackathon', '1 hour'
WHERE NOT EXISTS (SELECT 1 FROM events WHERE event_name = 'Project Submission');

INSERT INTO events (event_name, event_date, event_time, venue, description, category, duration)
SELECT 'Final Presentations', '2026-08-16', '10:00:00', 'Main Auditorium Stage',
 'Each team presents their solution to the judging panel with a live demo and Q&A round.', 'Hackathon', '1.5 hours'
WHERE NOT EXISTS (SELECT 1 FROM events WHERE event_name = 'Final Presentations');

INSERT INTO events (event_name, event_date, event_time, venue, description, category, duration)
SELECT 'Judging', '2026-08-16', '11:30:00', 'Judges Panel Room',
 'Judges deliberate and score each project based on innovation, impact, feasibility, and execution.', 'Judging', '1 hour'
WHERE NOT EXISTS (SELECT 1 FROM events WHERE event_name = 'Judging');

INSERT INTO events (event_name, event_date, event_time, venue, description, category, duration)
SELECT 'Prize Distribution', '2026-08-16', '12:30:00', 'Main Auditorium Stage',
 'Winners are announced and prizes are distributed, followed by closing remarks and group photos.', 'Ceremony', '1 hour'
WHERE NOT EXISTS (SELECT 1 FROM events WHERE event_name = 'Prize Distribution');

-- FAQs
INSERT INTO faqs (question, answer, category)
SELECT 'When is the hackathon?', 'The Community Hackathon for Social Innovation will take place on 15th August 2026, starting at 9:00 AM and running for a full 24 hours at the College Auditorium.', 'Hackathon'
WHERE NOT EXISTS (SELECT 1 FROM faqs WHERE question = 'When is the hackathon?');

INSERT INTO faqs (question, answer, category)
SELECT 'Who can participate?', 'Any student currently enrolled in a college or university can participate. Both beginners and experienced developers are welcome to join.', 'Registration'
WHERE NOT EXISTS (SELECT 1 FROM faqs WHERE question = 'Who can participate?');

INSERT INTO faqs (question, answer, category)
SELECT 'How many members can be in one team?', 'Each team can have a minimum of 2 and a maximum of 4 members, including the team leader.', 'Teams'
WHERE NOT EXISTS (SELECT 1 FROM faqs WHERE question = 'How many members can be in one team?');

INSERT INTO faqs (question, answer, category)
SELECT 'Is registration free?', 'Yes, registration for the Community Hackathon for Social Innovation is completely free for all eligible participants.', 'Registration'
WHERE NOT EXISTS (SELECT 1 FROM faqs WHERE question = 'Is registration free?');

INSERT INTO faqs (question, answer, category)
SELECT 'Can I participate without a team?', 'Yes, you can register individually and we will help match you with other solo participants to form a full team before the event begins.', 'Teams'
WHERE NOT EXISTS (SELECT 1 FROM faqs WHERE question = 'Can I participate without a team?');

INSERT INTO faqs (question, answer, category)
SELECT 'What type of projects can we build?', 'Projects must address a real-world social problem in areas such as Education, Healthcare, Environment, Agriculture, Smart Cities, or Women Safety.', 'Projects'
WHERE NOT EXISTS (SELECT 1 FROM faqs WHERE question = 'What type of projects can we build?');

INSERT INTO faqs (question, answer, category)
SELECT 'Which technologies can we use?', 'You are free to use any technology stack — web, mobile, AI/ML, IoT, or cloud-based solutions — as long as it effectively solves the chosen problem statement.', 'Projects'
WHERE NOT EXISTS (SELECT 1 FROM faqs WHERE question = 'Which technologies can we use?');

INSERT INTO faqs (question, answer, category)
SELECT 'Can we use AI tools?', 'Yes, using AI tools and APIs such as ChatGPT, GitHub Copilot, or other assistants is allowed and encouraged to boost productivity during the hackathon.', 'Projects'
WHERE NOT EXISTS (SELECT 1 FROM faqs WHERE question = 'Can we use AI tools?');

INSERT INTO faqs (question, answer, category)
SELECT 'What is the project submission deadline?', 'All projects must be submitted through the official portal by 9:00 AM on the second day, exactly 24 hours after the hackathon begins.', 'Hackathon'
WHERE NOT EXISTS (SELECT 1 FROM faqs WHERE question = 'What is the project submission deadline?');

INSERT INTO faqs (question, answer, category)
SELECT 'How will projects be judged?', 'Projects are evaluated based on innovation, social impact, technical execution, feasibility, and the quality of the final presentation.', 'Judging'
WHERE NOT EXISTS (SELECT 1 FROM faqs WHERE question = 'How will projects be judged?');

INSERT INTO faqs (question, answer, category)
SELECT 'What are the prizes?', 'The top three teams will receive cash prizes along with trophies and certificates — ₹25,000 for first place, ₹15,000 for second, and ₹10,000 for third.', 'Prizes'
WHERE NOT EXISTS (SELECT 1 FROM faqs WHERE question = 'What are the prizes?');

INSERT INTO faqs (question, answer, category)
SELECT 'Will participants receive certificates?', 'Yes, every participant who completes the hackathon will receive a digital certificate of participation, regardless of whether their team wins a prize.', 'Prizes'
WHERE NOT EXISTS (SELECT 1 FROM faqs WHERE question = 'Will participants receive certificates?');
