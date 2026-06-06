from datetime import datetime
import uuid
from extensions import db
import json
from sqlalchemy import DateTime, func

class Follow(db.Model):
    __tablename__ = 'follows'
 
    id           = db.Column(db.Integer, primary_key=True)
    follower_id  = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    following_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)
 
    __table_args__ = (
        db.UniqueConstraint('follower_id', 'following_id', name='uq_follow'),
    )
 
    follower  = db.relationship('User', foreign_keys=[follower_id],  backref='following_rel')
    following = db.relationship('User', foreign_keys=[following_id], backref='followers_rel')
 
    def to_dict(self):
        return {
            'id':           self.id,
            'follower_id':  self.follower_id,
            'following_id': self.following_id,
            'created_at':   self.created_at.isoformat(),
        }

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True)
    email = db.Column(db.String(120), unique=True)
    phone = db.Column(db.String(30), nullable=True)
    password = db.Column(db.String(200))
    full_name = db.Column(db.String(120), nullable=True)
    is_verified = db.Column(db.Boolean, default=False)
    email_verified = db.Column(db.Boolean, default=False)
    phone_verified = db.Column(db.Boolean, default=False)
    nmc_number = db.Column(db.String(100), nullable=True)
    degree = db.Column(db.String(100), nullable=True)
    verification_state = db.Column(db.String(50), default='pending')
    is_admin = db.Column(db.Boolean, default=False)
    google_id = db.Column(db.String(100), unique=True, nullable=True)
    zotero_user_id  = db.Column(db.String, nullable=True)
    zotero_api_key  = db.Column(db.String, nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'full_name': self.full_name,
            'phone': self.phone,
            'is_verified': self.is_verified,
            'email_verified': self.email_verified,
            'phone_verified': self.phone_verified,
            'nmc_number': self.nmc_number,
            'degree': self.degree,
            'verification_state': self.verification_state,
            'is_admin': self.is_admin
        }


class OtpCode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_email = db.Column(db.String(120), nullable=False)
    user_phone = db.Column(db.String(30), nullable=False)
    code = db.Column(db.String(10), nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.now())


class Group(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))


class GroupMember(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey("group.id"))
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))


class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer)
    sender_id = db.Column(db.String(120))  # email
    sender_name = db.Column(db.String(200))
    sender_photo = db.Column(db.String(300))
    receiver_id = db.Column(db.Integer, nullable=True)
    group_id = db.Column(db.Integer, nullable=True)
    content = db.Column(db.Text, nullable=True)
    message_type = db.Column(db.String(20), default="text")
    file_url = db.Column(db.String(300), nullable=True)
    is_read = db.Column(db.Boolean, default=False)
    read_by = db.Column(db.Text)
    created_date = db.Column(db.DateTime, default=datetime.utcnow)
    reactions = db.Column(db.Text, nullable=True)
    is_pinned = db.Column(db.Boolean, default=False)
    pinned_by = db.Column(db.String(120), nullable=True)
    pinned_date = db.Column(db.DateTime, nullable=True)
    is_archived = db.Column(db.Boolean, default=False)
    archived_by = db.Column(db.String(120), nullable=True)
    archived_date = db.Column(db.DateTime, nullable=True)
    is_encrypted = db.Column(db.Boolean, default=False)
    iv = db.Column(db.Text, nullable=True)
    encrypted_content = db.Column(db.Text, nullable=True)
    encryption_key_id = db.Column(db.String(50), nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'conversation_id': self.conversation_id,
            'sender_id': self.sender_id,
            'sender_name': self.sender_name,
            'sender_photo': self.sender_photo,
            'content': self.content,
            'message_type': self.message_type,
            'file_url': self.file_url,
            'is_read': self.is_read,
            'read_by': json.loads(self.read_by) if self.read_by else [],
            'created_date': self.created_date.isoformat() if self.created_date else None,
            'reactions': json.loads(self.reactions) if self.reactions else {},
            'is_pinned': self.is_pinned,
            'pinned_by': self.pinned_by,
            'pinned_date': self.pinned_date.isoformat() if self.pinned_date else None,
            'is_archived': self.is_archived,
            'archived_by': self.archived_by,
            'archived_date': self.archived_date.isoformat() if self.archived_date else None,
            'is_encrypted': self.is_encrypted,
            'iv': self.iv,
            'encrypted_content': self.encrypted_content,
            'encryption_key_id': self.encryption_key_id,
        }

class JobPosting(db.Model):
    __tablename__ = "job_postings"
 
    id              = db.Column(db.Integer, primary_key=True)
    title           = db.Column(db.String(200), nullable=False)
    institution     = db.Column(db.String(200))
    location        = db.Column(db.String(200))
    employment_type = db.Column(db.String(50))   # full-time / part-time / locum / fellowship
    specialty       = db.Column(db.String(100))
    description     = db.Column(db.Text)
    requirements    = db.Column(db.Text)
 
    # Salary
    salary_min      = db.Column(db.Float)
    salary_max      = db.Column(db.Float)
    salary_currency = db.Column(db.String(10), default="INR")
    salary_period   = db.Column(db.String(20), default="monthly")  # monthly / annual
 
    contact_email   = db.Column(db.String(200))
    deadline        = db.Column(db.String(50))   # ISO date string e.g. "2025-09-30"
    posted_by       = db.Column(db.String(200), nullable=False)  # email of poster
    is_active       = db.Column(db.Boolean, default=True)
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at      = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
 
    # Relationship: one posting → many applications
    applications    = db.relationship("JobApplication", backref="job", lazy=True, cascade="all, delete-orphan")
 
    def to_dict(self):
        return {
            "id":               self.id,
            "title":            self.title,
            "institution":      self.institution,
            "location":         self.location,
            "employment_type":  self.employment_type,
            "specialty":        self.specialty,
            "description":      self.description,
            "requirements":     self.requirements,
            "salary_min":       self.salary_min,
            "salary_max":       self.salary_max,
            "salary_currency":  self.salary_currency,
            "salary_period":    self.salary_period,
            "contact_email":    self.contact_email,
            "deadline":         self.deadline,
            "posted_by":        self.posted_by,
            "is_active":        self.is_active,
            "application_count": len(self.applications),
            "created_at":       self.created_at.isoformat() if self.created_at else None,
        }
    
class JobApplication(db.Model):
    __tablename__ = "job_applications"
 
    id               = db.Column(db.Integer, primary_key=True)
    job_id           = db.Column(db.Integer, db.ForeignKey("job_postings.id"), nullable=False)
    applicant_email  = db.Column(db.String(200), nullable=False)
    applicant_name   = db.Column(db.String(200))
    cover_letter     = db.Column(db.Text)
    cv_url           = db.Column(db.String(500))   # Supabase public URL
    status           = db.Column(db.String(30), default="pending")  # pending / shortlisted / rejected
    created_at       = db.Column(db.DateTime, default=datetime.utcnow)
 
    def to_dict(self):
        return {
            "id":               self.id,
            "job_id":           self.job_id,
            "applicant_email":  self.applicant_email,
            "applicant_name":   self.applicant_name,
            "cover_letter":     self.cover_letter,
            "cv_url":           self.cv_url,
            "status":           self.status,
            "created_at":       self.created_at.isoformat() if self.created_at else None,
        }  
    
      
class MedMarketListing(db.Model):
    __tablename__ = "medmarket_listings"
 
    id             = db.Column(db.Integer, primary_key=True)
    title          = db.Column(db.String(200), nullable=False)
    category       = db.Column(db.String(50))   # equipment / pharma / service / education / software / other
    description    = db.Column(db.Text)
    price          = db.Column(db.Float)
    currency       = db.Column(db.String(10), default="INR")
    price_type     = db.Column(db.String(30), default="fixed")   # fixed / negotiable / contact / free
    condition      = db.Column(db.String(30))                    # new / like-new / good / fair
    location       = db.Column(db.String(200))
    contact_email  = db.Column(db.String(200))
    contact_phone  = db.Column(db.String(50))
    website_url    = db.Column(db.String(500))
    images         = db.Column(db.Text)     # comma-separated Supabase public URLs
    posted_by      = db.Column(db.String(200), nullable=False)
    is_active      = db.Column(db.Boolean, default=True)
    is_featured    = db.Column(db.Boolean, default=False)   # featured/sponsored listing
    view_count     = db.Column(db.Integer, default=0)
    enquiry_count  = db.Column(db.Integer, default=0)
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at     = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
 
    def to_dict(self):
        return {
            "id":            self.id,
            "title":         self.title,
            "category":      self.category,
            "description":   self.description,
            "price":         self.price,
            "currency":      self.currency,
            "price_type":    self.price_type,
            "condition":     self.condition,
            "location":      self.location,
            "contact_email": self.contact_email,
            "contact_phone": self.contact_phone,
            "website_url":   self.website_url,
            "images":        self.images.split(",") if self.images else [],
            "posted_by":     self.posted_by,
            "is_active":     self.is_active,
            "is_featured":   self.is_featured,
            "view_count":    self.view_count,
            "enquiry_count": self.enquiry_count,
            "created_at":    self.created_at.isoformat() if self.created_at else None,
        }
    
class Case(db.Model):
    __tablename__ = 'patient_case'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200))
    chief_complaint = db.Column(db.Text)
    description = db.Column(db.Text)
    patient_age = db.Column(db.Integer)
    patient_gender = db.Column(db.String(50))
    history = db.Column(db.Text)
    examination_findings = db.Column(db.Text)
    investigations = db.Column(db.Text)
    current_treatment = db.Column(db.Text)
    question = db.Column(db.Text)
    specialty_tags = db.Column(db.String(500))
    visibility = db.Column(db.String(20), default='public')
    status = db.Column(db.String(20), default='open')
    attachments = db.Column(db.String(500))
    created_by = db.Column(db.String(120))
    created_date = db.Column(db.DateTime, default=datetime.utcnow)
    discussion_count = db.Column(db.Integer, default=0)

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'chief_complaint': self.chief_complaint,
            'patient_age': self.patient_age,
            'patient_gender': self.patient_gender,
            'history': self.history,
            'examination_findings': self.examination_findings,
            'investigations': self.investigations,
            'current_treatment': self.current_treatment,
            'question': self.question,
            'specialty_tags': self.specialty_tags.split(',') if self.specialty_tags else [],
            'status': self.status,
            'created_by': self.created_by,
            'created_date': self.created_date.isoformat(),
            'discussion_count': self.discussion_count
        }


class PublicKey(db.Model):
    __tablename__ = 'public_keys'
    user_id    = db.Column(db.Text, primary_key=True)
    public_key = db.Column(db.Text, nullable=False)
    updated_at = db.Column(DateTime, server_default=func.now(), onupdate=func.now())


class Comment(db.Model):
    __tablename__ = 'case_comment'
    id = db.Column(db.Integer, primary_key=True)
    case_id = db.Column(db.Integer)
    user_id = db.Column(db.Integer)
    commenter_id = db.Column(db.String(120))
    commenter_name = db.Column(db.String(200))
    commenter_specialty = db.Column(db.String(200))
    commenter_qualifications = db.Column(db.Text)
    commenter_photo = db.Column(db.String(300))
    content = db.Column(db.Text)
    is_treatment_suggestion = db.Column(db.Boolean, default=False)
    likes = db.Column(db.Integer, default=0)
    dislikes = db.Column(db.Integer, default=0)
    liked_by = db.Column(db.Text)
    disliked_by = db.Column(db.Text)
    replies = db.Column(db.Text)
    created_date = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'case_id': self.case_id,
            'commenter_id': self.commenter_id,
            'commenter_name': self.commenter_name,
            'commenter_specialty': self.commenter_specialty,
            'commenter_qualifications': json.loads(self.commenter_qualifications) if self.commenter_qualifications else [],
            'commenter_photo': self.commenter_photo,
            'content': self.content,
            'is_treatment_suggestion': self.is_treatment_suggestion,
            'likes': self.likes,
            'dislikes': self.dislikes,
            'liked_by': json.loads(self.liked_by) if self.liked_by else [],
            'disliked_by': json.loads(self.disliked_by) if self.disliked_by else [],
            'replies': json.loads(self.replies) if self.replies else [],
            'created_date': self.created_date.isoformat()
        }


class DoctorProfile(db.Model):
    __tablename__ = 'doctor_profile'
    id = db.Column(db.Integer, primary_key=True)
    created_by = db.Column(db.String(120))
    full_name = db.Column(db.String(200))
    profile_photo = db.Column(db.String(300))
    specialty = db.Column(db.String(200))
    user_id= db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    sub_specialty = db.Column(db.String(200))
    qualifications = db.Column(db.Text)
    registration_number = db.Column(db.String(100))
    location_city = db.Column(db.String(200))
    location_country = db.Column(db.String(200))
    years_experience = db.Column(db.Integer)
    institution_name = db.Column(db.String(200))
    institution_type = db.Column(db.String(200))
    bio = db.Column(db.Text)
    interests = db.Column(db.Text)
    profile_visibility = db.Column(db.String(20), default='public')
    response_count = db.Column(db.Integer, default=0)
    helpful_votes_received = db.Column(db.Integer, default=0)
    created_date = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'created_by': self.created_by,
            'full_name': self.full_name,
            'profile_photo': self.profile_photo,
            'profile_visibility': self.profile_visibility or 'public',
            'user_id': self.user_id,
            'specialty': self.specialty,
            'sub_specialty': self.sub_specialty,
            'qualifications': json.loads(self.qualifications) if self.qualifications else [],
            'registration_number': self.registration_number,
            'location_city': self.location_city,
            'location_country': self.location_country,
            'years_experience': self.years_experience,
            'institution_name': self.institution_name,
            'institution_type': self.institution_type,
            'bio': self.bio,
            'interests': json.loads(self.interests) if self.interests else [],
            'response_count': self.response_count,
            'helpful_votes_received': self.helpful_votes_received,
            'created_date': self.created_date.isoformat()
        }


class MedicalEvent(db.Model):
    __tablename__ = 'medical_event'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200))
    description = db.Column(db.Text)
    event_type = db.Column(db.String(100))
    specialties = db.Column(db.Text)
    created_by = db.Column(db.String(120), nullable=True)
    date = db.Column(db.DateTime)
    time = db.Column(db.String(50))
    end_date = db.Column(db.DateTime)
    location_city = db.Column(db.String(200))
    location_country = db.Column(db.String(200))
    venue = db.Column(db.String(200))
    is_online = db.Column(db.Boolean, default=False)
    online_link = db.Column(db.String(300))
    registration_link = db.Column(db.String(300))
    is_free = db.Column(db.Boolean, default=True)
    price = db.Column(db.String(100))
    organizer = db.Column(db.String(200))
    image_url = db.Column(db.Text)
    attendees = db.Column(db.Text)
    interested = db.Column(db.Text)
    created_date = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'event_type': self.event_type,
            'specialties': json.loads(self.specialties) if self.specialties else [],
            'date': self.date.isoformat() if self.date else None,
            'time': self.time,
            'end_date': self.end_date.isoformat() if self.end_date else None,
            'location_city': self.location_city,
            'location_country': self.location_country,
            'venue': self.venue,
            'is_online': self.is_online,
            'online_link': self.online_link,
            'created_by': self.created_by,
            'registration_link': self.registration_link,
            'is_free': self.is_free,
            'price': self.price,
            'organizer': self.organizer,
            'image_url': self.image_url,
            'attendees': json.loads(self.attendees) if self.attendees else [],
            'interested': json.loads(self.interested) if self.interested else [],
            'created_date': self.created_date.isoformat()
        }


class Conversation(db.Model):
    __tablename__ = 'conversation'
    id = db.Column(db.Integer, primary_key=True)
    participants = db.Column(db.Text)
    participant_names = db.Column(db.Text)
    participant_photos = db.Column(db.Text)
    last_message = db.Column(db.Text)
    last_message_time = db.Column(db.DateTime, default=datetime.utcnow)
    last_message_sender = db.Column(db.String(120))
    unread_count = db.Column(db.Text)
    is_group = db.Column(db.Boolean, default=False)
    group_name = db.Column(db.String(200))
    created_date = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'participants': json.loads(self.participants) if self.participants else [],
            'participant_names': json.loads(self.participant_names) if self.participant_names else [],
            'participant_photos': json.loads(self.participant_photos) if self.participant_photos else [],
            'last_message': self.last_message,
            'last_message_time': self.last_message_time.isoformat() if self.last_message_time else None,
            'last_message_sender': self.last_message_sender,
            'unread_count': json.loads(self.unread_count) if self.unread_count else {},
            'is_group': self.is_group,
            'group_name': self.group_name,
            'created_date': self.created_date.isoformat()
        }


class Workshop(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200))
    link = db.Column(db.String(300))
    description = db.Column(db.Text)

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'link': self.link,
            'description': self.description
        }


class SavedReference(db.Model):
    __tablename__ = 'saved_references'
    id = db.Column(db.String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    pmid = db.Column(db.String, nullable=False)
    title = db.Column(db.Text)
    authors = db.Column(db.Text)
    abstract = db.Column(db.Text)
    year = db.Column(db.String)
    url = db.Column(db.String)
    saved_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'pmid', name='unique_user_paper'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'pmid': self.pmid,
            'title': self.title,
            'authors': self.authors,
            'abstract': self.abstract,
            'year': self.year,
            'url': self.url,
            'saved_at': self.saved_at.isoformat()
        }


class Forum(db.Model):
    __tablename__ = 'forum'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), unique=True)
    description = db.Column(db.Text)
    created_by = db.Column(db.String(120))
    created_date = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'created_by': self.created_by,
            'created_date': self.created_date.isoformat()
        }


class Thread(db.Model):
    __tablename__ = 'thread'
    id = db.Column(db.Integer, primary_key=True)
    forum_id = db.Column(db.Integer, db.ForeignKey('forum.id'))
    title = db.Column(db.String(300))
    content = db.Column(db.Text)
    created_by = db.Column(db.String(120))
    created_date = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'forum_id': self.forum_id,
            'title': self.title,
            'content': self.content,
            'created_by': self.created_by,
            'created_date': self.created_date.isoformat()
        }


class ThreadComment(db.Model):
    __tablename__ = 'thread_comment'
    id = db.Column(db.Integer, primary_key=True)
    thread_id = db.Column(db.Integer, db.ForeignKey('thread.id'))
    content = db.Column(db.Text)
    created_by = db.Column(db.String(120))
    created_date = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'thread_id': self.thread_id,
            'content': self.content,
            'created_by': self.created_by,
            'created_date': self.created_date.isoformat()
        }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONTACT GROUPS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class ContactGroup(db.Model):
    __tablename__ = 'contact_groups'

    id         = db.Column(db.Integer, primary_key=True)
    owner_id   = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name       = db.Column(db.String(100), nullable=False)
    color      = db.Column(db.String(20), default='teal')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    owner   = db.relationship('User', foreign_keys=[owner_id])
    members = db.relationship('ContactGroupMember', back_populates='group',
                              cascade='all, delete-orphan')

    def to_dict(self, include_members=True):
        data = {
            'id':           self.id,
            'name':         self.name,
            'color':        self.color,
            'created_at':   self.created_at.isoformat(),
            'member_count': len(self.members),
        }
        if include_members:
            data['members'] = [m.to_dict() for m in self.members]
        return data


class ContactGroupMember(db.Model):
    __tablename__ = 'contact_group_members'

    id       = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('contact_groups.id'), nullable=False)
    user_id  = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    added_at = db.Column(db.DateTime, default=datetime.utcnow)

    group = db.relationship('ContactGroup', back_populates='members')
    user  = db.relationship('User', foreign_keys=[user_id])

    __table_args__ = (
        db.UniqueConstraint('group_id', 'user_id', name='unique_group_member'),
    )

    def to_dict(self):
        return {
            'user_id':    self.user_id,
            'added_at':   self.added_at.isoformat(),
            'full_name':  self.user.full_name  if self.user else '',
            'email':      self.user.email      if self.user else '',
            'specialty':  '',   # DoctorProfile holds specialty, not User — fine to leave blank
            'avatar_url': '',
        }
    


class Prescription(db.Model):
    __tablename__ = 'prescriptions'

    id = db.Column(db.Integer, primary_key=True)
    disease = db.Column(db.String(200), nullable=False, index=True)
    icd_code = db.Column(db.String(20))
    source = db.Column(db.String(100))
    last_updated = db.Column(db.String(20))
    medications = db.Column(db.JSON)
    contraindications = db.Column(db.JSON)
    patient_groups = db.Column(db.JSON)

    def to_dict(self):
        return {
            'disease': self.disease,
            'icd_code': self.icd_code,
            'source': self.source,
            'last_updated': self.last_updated,
            'medications': self.medications,
            'contraindications': self.contraindications,
            'patient_groups': self.patient_groups,
        }