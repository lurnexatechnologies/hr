import uuid
from decimal import Decimal
from django.shortcuts import render, redirect
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.http import JsonResponse, Http404
from core.dynamodb_service import (
    UsersTable, EmployeesTable, DepartmentsTable, OKRsTable,
    FeedbackCyclesTable, FeedbackTemplatesTable, FeedbackCompetenciesTable,
    FeedbackQuestionsTable, FeedbackReviewAssignmentsTable,
    FeedbackReviewResponsesTable, FeedbackDevelopmentPlansTable,
    FeedbackAuditLogsTable
)
from core.utils import get_local_now, send_notification

# Audit Log Helper
def log_feedback_action(request, action, details):
    try:
        user = request.user
        log_id = str(uuid.uuid4())
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        ip = x_forwarded_for.split(',')[0] if x_forwarded_for else request.META.get('REMOTE_ADDR', '127.0.0.1')
        browser = request.META.get('HTTP_USER_AGENT', 'Unknown')
        
        log_item = {
            'LogID': log_id,
            'Timestamp': get_local_now().isoformat(),
            'UserID': getattr(user, 'employee_id', user.username),
            'UserEmail': getattr(user, 'email', 'unknown'),
            'Action': action,
            'OrgID': getattr(user, 'org_id', 'Global'),
            'Details': details,
            'IP': ip,
            'Browser': browser
        }
        FeedbackAuditLogsTable.put_item(log_item)
    except Exception as e:
        print(f"Error logging feedback audit: {e}")

# Main 360 Feedback Hub
class Feedback360HubView(LoginRequiredMixin, View):
    def get(self, request):
        user = request.user
        org_id = user.org_id
        role = user.role
        eid = user.employee_id
        
        # Super admin cannot participate in ordinary 360 feedback, but can configure settings
        if role == 'Super admin':
            # Redirect to cycles or config
            return redirect('feedback_cycles')

        # Fetch basic context data
        cycles = FeedbackCyclesTable.scan(
            FilterExpression="OrgID = :oid",
            ExpressionAttributeValues={":oid": org_id}
        )
        
        # Dynamic stats based on role
        stats = {
            'total_cycles': len(cycles),
            'active_cycles': len([c for c in cycles if c.get('Status') == 'Active']),
            'pending_reviews': 0,
            'completed_reviews': 0,
            'completion_rate': 100
        }

        # Query reviewer assignments
        all_assignments = FeedbackReviewAssignmentsTable.scan(
            FilterExpression="OrgID = :oid",
            ExpressionAttributeValues={":oid": org_id}
        )
        
        # User role specifics
        my_pending_reviews = []
        my_submitted_reviews = []
        my_reports = []
        
        for a in all_assignments:
            # Reviews requested from the user
            if a.get('ReviewerID') == eid:
                if a.get('Status') == 'Pending Review':
                    my_pending_reviews.append(a)
                elif a.get('Status') == 'Submitted':
                    my_submitted_reviews.append(a)
            
            # Reports owned by user
            if a.get('RevieweeID') == eid and a.get('Status') == 'Submitted' and a.get('Relationship') == 'Self':
                my_reports.append(a)

        stats['pending_reviews'] = len(my_pending_reviews)
        stats['completed_reviews'] = len(my_submitted_reviews)
        total_assigned = stats['pending_reviews'] + stats['completed_reviews']
        if total_assigned > 0:
            stats['completion_rate'] = int((stats['completed_reviews'] / total_assigned) * 100)

        # Team stats for Manager
        team_members = []
        team_stats = []
        if role == 'Manager':
            from core.dynamodb_service import ReportingHierarchyTable
            subs = [s.get('EmployeeID') for s in ReportingHierarchyTable.scan(
                FilterExpression="ManagerID = :mid",
                ExpressionAttributeValues={":mid": eid}
            ) if s.get('EmployeeID')]
            all_employees = EmployeesTable.scan(
                FilterExpression="OrgID = :oid",
                ExpressionAttributeValues={":oid": org_id}
            )
            team_members = [e for e in all_employees if e.get('EmployeeID') in subs]
            
            # Subordinates review completion tracking
            for sub in team_members:
                sub_id = sub.get('EmployeeID')
                sub_assigns = [a for a in all_assignments if a.get('RevieweeID') == sub_id]
                total = len(sub_assigns)
                done = len([a for a in sub_assigns if a.get('Status') == 'Submitted'])
                rate = int((done / total) * 100) if total > 0 else 0
                team_stats.append({
                    'EmployeeID': sub_id,
                    'Name': f"{sub.get('FirstName', '')} {sub.get('LastName', '')}",
                    'Designation': sub.get('Designation', ''),
                    'TotalReviewers': total,
                    'DoneReviewers': done,
                    'CompletionRate': rate
                })

        # HR Admin Analytics
        hr_analytics = {}
        if role == 'HR ADMIN':
            # Count total assignments, completion rates org-wide
            total_org_reviews = len(all_assignments)
            completed_org_reviews = len([a for a in all_assignments if a.get('Status') == 'Submitted'])
            hr_analytics = {
                'total_reviews': total_org_reviews,
                'completed_reviews': completed_org_reviews,
                'pending_reviews': total_org_reviews - completed_org_reviews,
                'rate': int((completed_org_reviews / total_org_reviews) * 100) if total_org_reviews > 0 else 0
            }

        return render(request, 'core/feedback360/hub.html', {
            'stats': stats,
            'my_pending_reviews': my_pending_reviews,
            'my_submitted_reviews': my_submitted_reviews,
            'my_reports': my_reports,
            'team_members': team_members,
            'team_stats': team_stats,
            'hr_analytics': hr_analytics,
            'cycles': cycles
        })

# Competency Management
class FeedbackCompetenciesView(LoginRequiredMixin, View):
    def get(self, request):
        if request.user.role not in ('Super admin', 'HR ADMIN'):
            messages.error(request, "Access denied.")
            return redirect('feedback_hub')
            
        org_id = request.user.org_id
        competencies = FeedbackCompetenciesTable.scan(
            FilterExpression="OrgID = :oid",
            ExpressionAttributeValues={":oid": org_id}
        )
        return render(request, 'core/feedback360/competencies.html', {
            'competencies': competencies
        })
        
    def post(self, request):
        if request.user.role not in ('Super admin', 'HR ADMIN'):
            return JsonResponse({'success': False, 'message': 'Permission denied'})
            
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        weight = request.POST.get('weight', '10')
        indicators = [i.strip() for i in request.POST.get('indicators', '').split(',') if i.strip()]
        
        if not name or not description:
            messages.error(request, "Name and description are required.")
            return redirect('feedback_competencies')
            
        try:
            cid = str(uuid.uuid4())
            item = {
                'CompetencyID': cid,
                'OrgID': request.user.org_id,
                'Name': name,
                'Description': description,
                'Weight': Decimal(weight),
                'BehaviorIndicators': indicators
            }
            FeedbackCompetenciesTable.put_item(item)
            log_feedback_action(request, 'CREATE_COMPETENCY', f"Created competency: {name}")
            messages.success(request, f"Competency '{name}' added successfully.")
        except Exception as e:
            messages.error(request, f"Error saving competency: {e}")
            
        return redirect('feedback_competencies')

# Question Bank Management
class FeedbackQuestionBankView(LoginRequiredMixin, View):
    def get(self, request):
        if request.user.role not in ('Super admin', 'HR ADMIN'):
            messages.error(request, "Access denied.")
            return redirect('feedback_hub')
            
        org_id = request.user.org_id
        questions = FeedbackQuestionsTable.scan(
            FilterExpression="OrgID = :oid",
            ExpressionAttributeValues={":oid": org_id}
        )
        competencies = FeedbackCompetenciesTable.scan(
            FilterExpression="OrgID = :oid",
            ExpressionAttributeValues={":oid": org_id}
        )
        
        return render(request, 'core/feedback360/questions.html', {
            'questions': questions,
            'competencies': competencies
        })
        
    def post(self, request):
        if request.user.role not in ('Super admin', 'HR ADMIN'):
            return JsonResponse({'success': False, 'message': 'Permission denied'})
            
        q_text = request.POST.get('question_text', '').strip()
        category = request.POST.get('category', '').strip()
        q_type = request.POST.get('question_type', 'RatingScale').strip()
        is_mandatory = request.POST.get('is_mandatory') == 'true'
        options = [o.strip() for o in request.POST.get('options', '').split(',') if o.strip()]
        
        if not q_text or not category:
            messages.error(request, "Question text and competency category are required.")
            return redirect('feedback_questions')
            
        try:
            qid = str(uuid.uuid4())
            item = {
                'QuestionID': qid,
                'OrgID': request.user.org_id,
                'QuestionText': q_text,
                'Category': category,
                'QuestionType': q_type,
                'IsMandatory': is_mandatory,
                'Options': options
            }
            FeedbackQuestionsTable.put_item(item)
            log_feedback_action(request, 'CREATE_QUESTION', f"Created question in category {category}")
            messages.success(request, "Question added to bank successfully.")
        except Exception as e:
            messages.error(request, f"Error: {e}")
            
        return redirect('feedback_questions')

# Template Management
class FeedbackTemplatesView(LoginRequiredMixin, View):
    def get(self, request):
        if request.user.role not in ('Super admin', 'HR ADMIN'):
            messages.error(request, "Access denied.")
            return redirect('feedback_hub')
            
        org_id = request.user.org_id
        templates_list = FeedbackTemplatesTable.scan(
            FilterExpression="OrgID = :oid",
            ExpressionAttributeValues={":oid": org_id}
        )
        competencies = FeedbackCompetenciesTable.scan(
            FilterExpression="OrgID = :oid",
            ExpressionAttributeValues={":oid": org_id}
        )
        questions = FeedbackQuestionsTable.scan(
            FilterExpression="OrgID = :oid",
            ExpressionAttributeValues={":oid": org_id}
        )
        
        return render(request, 'core/feedback360/templates.html', {
            'templates': templates_list,
            'competencies': competencies,
            'questions': questions
        })
        
    def post(self, request):
        if request.user.role != 'Super admin':
            messages.error(request, "Only Super Admins can configure/modify evaluation templates.")
            return redirect('feedback_templates')
            
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        comp_ids = request.POST.getlist('competency_ids')
        q_ids = request.POST.getlist('question_ids')
        
        if not name or not comp_ids:
            messages.error(request, "Template name and competency mappings are required.")
            return redirect('feedback_templates')
            
        try:
            tid = str(uuid.uuid4())
            item = {
                'TemplateID': tid,
                'OrgID': request.user.org_id,
                'Name': name,
                'Description': description,
                'Competencies': comp_ids,
                'Questions': q_ids
            }
            FeedbackTemplatesTable.put_item(item)
            log_feedback_action(request, 'CREATE_TEMPLATE', f"Created template: {name}")
            messages.success(request, f"Template '{name}' configured successfully.")
        except Exception as e:
            messages.error(request, f"Error: {e}")
            
        return redirect('feedback_templates')

# Feedback Cycles Configuration & Workflows
class FeedbackCyclesView(LoginRequiredMixin, View):
    def get(self, request):
        if request.user.role not in ('Super admin', 'HR ADMIN'):
            messages.error(request, "Access denied.")
            return redirect('feedback_hub')
            
        org_id = request.user.org_id
        cycles = FeedbackCyclesTable.scan(
            FilterExpression="OrgID = :oid",
            ExpressionAttributeValues={":oid": org_id}
        )
        templates = FeedbackTemplatesTable.scan(
            FilterExpression="OrgID = :oid",
            ExpressionAttributeValues={":oid": org_id}
        )
        
        # Get active employees and departments (excluding Super Admin and Platform Admin)
        all_users = UsersTable.scan(
            FilterExpression="OrgID = :oid",
            ExpressionAttributeValues={":oid": org_id}
        )
        admin_user_ids = {u.get('UserID') for u in all_users if (u.get('Role') or '').strip().upper() in ['SUPER ADMIN', 'SUPERADMIN', 'PLATFORM ADMIN', 'PLATFORM SUPER ADMIN']}
        all_emp_raw = EmployeesTable.scan(
            FilterExpression="OrgID = :oid",
            ExpressionAttributeValues={":oid": org_id}
        )
        all_emp = [e for e in all_emp_raw if e.get('UserID') not in admin_user_ids]
        depts = DepartmentsTable.scan(
            FilterExpression="OrgID = :oid",
            ExpressionAttributeValues={":oid": org_id}
        )
        
        return render(request, 'core/feedback360/cycles.html', {
            'cycles': cycles,
            'templates': templates,
            'employees': all_emp,
            'departments': depts
        })
        
    def post(self, request):
        if request.user.role != 'HR ADMIN':
            messages.error(request, "Only HR Administrators can configure or launch Feedback Cycles.")
            return redirect('feedback_cycles')
            
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')
        template_id = request.POST.get('template_id')
        
        allow_self = request.POST.get('allow_self') == 'on'
        allow_peer = request.POST.get('allow_peer') == 'on'
        allow_upward = request.POST.get('allow_upward') == 'on'
        allow_client = request.POST.get('allow_client') == 'on'
        anonymous = request.POST.get('anonymous') == 'on'
        
        min_rev = int(request.POST.get('min_reviewer', 3))
        max_rev = int(request.POST.get('max_reviewer', 10))
        
        weight_mgr = int(request.POST.get('weight_mgr', 40))
        weight_self = int(request.POST.get('weight_self', 10))
        weight_peer = int(request.POST.get('weight_peer', 25))
        weight_upward = int(request.POST.get('weight_upward', 15))
        weight_client = int(request.POST.get('weight_client', 10))
        
        target_employees = request.POST.getlist('target_employees')
        
        if not name or not start_date or not end_date or not template_id:
            messages.error(request, "Name, timelines, and template selection are mandatory.")
            return redirect('feedback_cycles')
            
        try:
            cid = str(uuid.uuid4())
            cycle_rec = {
                'CycleID': cid,
                'OrgID': request.user.org_id,
                'Name': name,
                'Description': description,
                'StartDate': start_date,
                'EndDate': end_date,
                'TemplateID': template_id,
                'Status': 'Draft',
                'Anonymous': anonymous,
                'Rules': {
                    'AllowSelf': allow_self,
                    'AllowPeer': allow_peer,
                    'AllowUpward': allow_upward,
                    'AllowClient': allow_client,
                    'MinReviewers': min_rev,
                    'MaxReviewers': max_rev
                },
                'Weightages': {
                    'Manager': weight_mgr,
                    'Self': weight_self,
                    'Peer': weight_peer,
                    'DirectReport': weight_upward,
                    'Client': weight_client
                },
                'Employees': target_employees,
                'CreatedAt': get_local_now().isoformat()
            }
            FeedbackCyclesTable.put_item(cycle_rec)
            log_feedback_action(request, 'CREATE_CYCLE', f"Created feedback cycle: {name}")
            messages.success(request, f"Feedback cycle '{name}' created in Draft state.")
        except Exception as e:
            messages.error(request, f"Error launching cycle: {e}")
            
        return redirect('feedback_cycles')

# Cycle Status Transition (Launch, Close, Publish)
class FeedbackCycleTransitionView(LoginRequiredMixin, View):
    def post(self, request, cycle_id):
        if request.user.role != 'HR ADMIN':
            return JsonResponse({'success': False, 'message': 'Only HR Admin can update cycle state.'})
            
        action = request.POST.get('action')
        org_id = request.user.org_id
        
        try:
            cycle = FeedbackCyclesTable.get_item({'CycleID': cycle_id})
            if not cycle or cycle.get('OrgID') != org_id:
                return JsonResponse({'success': False, 'message': 'Cycle not found.'})
                
            old_status = cycle.get('Status')
            
            if action == 'nominate':
                cycle['Status'] = 'Nominated'
                # Notify managers to nominate reviewers
                all_emp = EmployeesTable.scan()
                emp_name_map = {e.get('EmployeeID'): f"{e.get('FirstName', '')} {e.get('LastName', '')}" for e in all_emp}
                for target_id in cycle.get('Employees', []):
                    # Find manager
                    from core.dynamodb_service import ReportingHierarchyTable
                    relations = [r for r in ReportingHierarchyTable.scan() if r.get('EmployeeID') == target_id]
                    if relations:
                        mgr_id = relations[0].get('ManagerID')
                        target_name = emp_name_map.get(target_id, target_id)
                        send_notification(
                            employee_id=mgr_id,
                            title="Nomination Request",
                            message=f"Please nominate reviewers for {target_name} in cycle '{cycle.get('Name')}'",
                            n_type='System',
                            icon='fa-users-cog',
                            org_id=org_id
                        )
                
            elif action == 'launch':
                cycle['Status'] = 'Active'
                # Initialize review assignments
                all_assignments = [a for a in FeedbackReviewAssignmentsTable.scan() if a.get('CycleID') == cycle_id]
                for a in all_assignments:
                    if a.get('Status') == 'Approved':
                        a['Status'] = 'Pending Review'
                        FeedbackReviewAssignmentsTable.put_item(a)
                        # Notify reviewers
                        send_notification(
                            employee_id=a.get('ReviewerID'),
                            title="360° Review Required",
                            message=f"You have been designated to submit 360 feedback for {a.get('RevieweeName')}",
                            n_type='System',
                            icon='fa-signature',
                            org_id=org_id
                        )
                        
            elif action == 'close':
                cycle['Status'] = 'Closed'
                
            elif action == 'publish':
                cycle['Status'] = 'Published'
                # Aggregation engine triggers to lock scores & build final report
                # Notify employees reports are ready
                for target_id in cycle.get('Employees', []):
                    send_notification(
                        employee_id=target_id,
                        title="360° Report Published",
                        message=f"Your feedback report for cycle '{cycle.get('Name')}' is now ready to view.",
                        n_type='System',
                        icon='fa-chart-line',
                        org_id=org_id
                    )
                    
            FeedbackCyclesTable.put_item(cycle)
            log_feedback_action(request, 'TRANSITION_CYCLE', f"Status of {cycle.get('Name')} moved from {old_status} to {cycle.get('Status')}")
            return JsonResponse({'success': True, 'new_status': cycle['Status']})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})

# Reviewer Nomination & Manager Approvals
class ReviewerNominationView(LoginRequiredMixin, View):
    def get(self, request):
        user = request.user
        org_id = user.org_id
        role = user.role
        eid = user.employee_id
        
        # Load cycle requesting nominations
        cycles = [c for c in FeedbackCyclesTable.scan() if c.get('OrgID') == org_id and c.get('Status') in ('Nominated', 'Active')]
        all_emp = [e for e in EmployeesTable.scan() if e.get('OrgID') == org_id]
        
        nominations = []
        approvals_pending = []
        
        # Filter subordinates for Manager review
        sub_ids = []
        if role == 'Manager':
            from core.dynamodb_service import ReportingHierarchyTable
            sub_ids = [s.get('EmployeeID') for s in ReportingHierarchyTable.scan() if s.get('ManagerID') == eid]
            
        # Get existing assignments
        all_assigns = [a for a in FeedbackReviewAssignmentsTable.scan() if a.get('OrgID') == org_id]
        
        for c in cycles:
            for target_id in c.get('Employees', []):
                # Manager nominates for their team members; Employees nominate for themselves
                if (role == 'Manager' and target_id in sub_ids) or (target_id == eid):
                    target_emp = next((e for e in all_emp if e.get('EmployeeID') == target_id), None)
                    emp_assigns = [a for a in all_assigns if a.get('CycleID') == c.get('CycleID') and a.get('RevieweeID') == target_id]
                    nominations.append({
                        'Cycle': c,
                        'Employee': target_emp,
                        'NominatedCount': len(emp_assigns),
                        'Nominees': emp_assigns
                    })
                # HR sees all pending nominations to approve
                if role == 'HR ADMIN':
                    target_emp = next((e for e in all_emp if e.get('EmployeeID') == target_id), None)
                    emp_assigns = [a for a in all_assigns if a.get('CycleID') == c.get('CycleID') and a.get('RevieweeID') == target_id]
                    approvals_pending.append({
                        'Cycle': c,
                        'Employee': target_emp,
                        'NominatedCount': len(emp_assigns),
                        'Nominees': emp_assigns
                    })
                    
        return render(request, 'core/feedback360/reviewer_nominations.html', {
            'nominations': nominations,
            'approvals_pending': approvals_pending,
            'employees': all_emp,
            'cycles': cycles
        })
        
    def post(self, request):
        # Handle nominations creation
        cycle_id = request.POST.get('cycle_id')
        reviewee_id = request.POST.get('reviewee_id')
        reviewer_id = request.POST.get('reviewer_id')
        relationship = request.POST.get('relationship')
        
        if not cycle_id or not reviewee_id or not reviewer_id or not relationship:
            messages.error(request, "Missing nomination parameters.")
            return redirect('reviewer_nominations')
            
        try:
            # Verify employee records
            all_emp = EmployeesTable.scan()
            reviewer = next((e for e in all_emp if e.get('EmployeeID') == reviewer_id), None)
            reviewee = next((e for e in all_emp if e.get('EmployeeID') == reviewee_id), None)
            
            if not reviewer or not reviewee:
                messages.error(request, "Employee records not found.")
                return redirect('reviewer_nominations')
                
            aid = str(uuid.uuid4())
            item = {
                'AssignmentID': aid,
                'OrgID': request.user.org_id,
                'CycleID': cycle_id,
                'RevieweeID': reviewee_id,
                'RevieweeName': f"{reviewee.get('FirstName', '')} {reviewee.get('LastName', '')}",
                'ReviewerID': reviewer_id,
                'ReviewerName': f"{reviewer.get('FirstName', '')} {reviewer.get('LastName', '')}",
                'ReviewerRole': reviewer.get('Designation', 'Associate'),
                'Relationship': relationship,
                'Status': 'Pending Approval',
                'NominatedBy': request.user.employee_id
            }
            FeedbackReviewAssignmentsTable.put_item(item)
            log_feedback_action(request, 'NOMINATE_REVIEWER', f"Nominated reviewer {reviewer_id} for {reviewee_id}")
            messages.success(request, "Reviewer nomination submitted for HR approval.")
        except Exception as e:
            messages.error(request, f"Error submitting nomination: {e}")
            
        return redirect('reviewer_nominations')

# Approve/Reject Nomination Workflow (HR)
class ApproveNominationView(LoginRequiredMixin, View):
    def post(self, request, assignment_id):
        if request.user.role != 'HR ADMIN':
            return JsonResponse({'success': False, 'message': 'Only HR can approve review assignments.'})
            
        action = request.POST.get('action') # approve / reject / remove
        
        try:
            assign = FeedbackReviewAssignmentsTable.get_item({'AssignmentID': assignment_id})
            if not assign or assign.get('OrgID') != request.user.org_id:
                return JsonResponse({'success': False, 'message': 'Assignment not found.'})
                
            if action == 'approve':
                assign['Status'] = 'Approved'
                FeedbackReviewAssignmentsTable.put_item(assign)
                log_feedback_action(request, 'APPROVE_NOMINATION', f"Approved assignment: {assignment_id}")
                return JsonResponse({'success': True, 'message': 'Nomination approved.'})
            elif action == 'reject':
                assign['Status'] = 'Rejected'
                FeedbackReviewAssignmentsTable.put_item(assign)
                log_feedback_action(request, 'REJECT_NOMINATION', f"Rejected assignment: {assignment_id}")
                return JsonResponse({'success': True, 'message': 'Nomination rejected.'})
            elif action == 'delete':
                FeedbackReviewAssignmentsTable.delete_item({'AssignmentID': assignment_id})
                log_feedback_action(request, 'DELETE_NOMINATION', f"Removed nomination: {assignment_id}")
                return JsonResponse({'success': True, 'message': 'Nomination deleted.'})
                
            return JsonResponse({'success': False, 'message': 'Invalid action'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})

# Complete Evaluation / Answer Questions
class EvaluateSurveyView(LoginRequiredMixin, View):
    def get(self, request, assignment_id):
        org_id = request.user.org_id
        eid = request.user.employee_id
        
        # Load assignment details
        assignment = FeedbackReviewAssignmentsTable.get_item({'AssignmentID': assignment_id})
        if not assignment or assignment.get('OrgID') != org_id:
            raise Http404("Review assignment not found.")
            
        # Permission constraint - only designated reviewer can evaluate
        if assignment.get('ReviewerID') != eid:
            messages.error(request, "Permission denied. You are not authorized to complete this evaluation.")
            return redirect('feedback_hub')
            
        # Get Cycle configuration
        cycle = FeedbackCyclesTable.get_item({'CycleID': assignment.get('CycleID')})
        if not cycle or cycle.get('Status') != 'Active':
            messages.error(request, "Evaluation cycle is not active.")
            return redirect('feedback_hub')
            
        # Load questions from template
        template = FeedbackTemplatesTable.get_item({'TemplateID': cycle.get('TemplateID')})
        if not template:
            messages.error(request, "Evaluation template configuration is missing.")
            return redirect('feedback_hub')
            
        all_questions = FeedbackQuestionsTable.scan()
        selected_questions = [q for q in all_questions if q.get('QuestionID') in template.get('Questions', [])]
        
        # Look for draft response if exists
        all_responses = FeedbackReviewResponsesTable.scan()
        draft = next((r for r in all_responses if r.get('AssignmentID') == assignment_id), None)
        answers = draft.get('Answers', {}) if draft else {}
        overall_comment = draft.get('Comments', '') if draft else {}
        
        return render(request, 'core/feedback360/evaluate.html', {
            'assignment': assignment,
            'cycle': cycle,
            'questions': selected_questions,
            'answers': answers,
            'overall_comment': overall_comment
        })
        
    def post(self, request, assignment_id):
        org_id = request.user.org_id
        eid = request.user.employee_id
        
        assignment = FeedbackReviewAssignmentsTable.get_item({'AssignmentID': assignment_id})
        if not assignment or assignment.get('OrgID') != org_id or assignment.get('ReviewerID') != eid:
            return JsonResponse({'success': False, 'message': 'Access denied.'})
            
        # Save Draft vs Submit Final
        is_draft = request.POST.get('is_draft') == 'true'
        comments = request.POST.get('overall_comments', '').strip()
        
        # Compile answers dict
        answers = {}
        for key, value in request.POST.items():
            if key.startswith('q_'):
                q_id = key.split('_')[1]
                answers[q_id] = value.strip()
                
        try:
            # Check for existing response
            all_responses = FeedbackReviewResponsesTable.scan()
            resp = next((r for r in all_responses if r.get('AssignmentID') == assignment_id), None)
            
            if not resp:
                resp_id = str(uuid.uuid4())
                resp = {
                    'ResponseID': resp_id,
                    'OrgID': org_id,
                    'AssignmentID': assignment_id,
                    'CycleID': assignment.get('CycleID'),
                    'RevieweeID': assignment.get('RevieweeID'),
                    'ReviewerID': eid,
                }
                
            resp['Answers'] = answers
            resp['Comments'] = comments
            resp['SubmittedAt'] = get_local_now().isoformat()
            
            # Put response
            FeedbackReviewResponsesTable.put_item(resp)
            
            if not is_draft:
                # Update assignment status
                assignment['Status'] = 'Submitted'
                FeedbackReviewAssignmentsTable.put_item(assignment)
                log_feedback_action(request, 'SUBMIT_FEEDBACK', f"Submitted review for assignment {assignment_id}")
                messages.success(request, "Evaluation submitted successfully.")
            else:
                log_feedback_action(request, 'SAVE_DRAFT_FEEDBACK', f"Saved review draft for assignment {assignment_id}")
                messages.success(request, "Draft saved successfully.")
                
            return redirect('feedback_hub')
        except Exception as e:
            messages.error(request, f"Error saving evaluation: {e}")
            return redirect('feedback_hub')

# Aggregated Reports & Calibration Views
class FeedbackReportView(LoginRequiredMixin, View):
    def get(self, request, cycle_id, employee_id):
        org_id = request.user.org_id
        user = request.user
        role = user.role
        eid = user.employee_id
        
        # Enforce Permissions
        # Target employee, manager, and HR admins can view reports. Super admin is excluded from viewing individual feedback contents.
        if role == 'Super admin':
            messages.error(request, "Super Admins are restricted from viewing individual performance evaluation details.")
            return redirect('feedback_hub')
            
        if role == 'Employee' and employee_id != eid:
            messages.error(request, "Access denied. You can only view your own report.")
            return redirect('feedback_hub')
            
        if role == 'Manager':
            # Verify if subordinate
            from core.dynamodb_service import ReportingHierarchyTable
            subs = [s.get('EmployeeID') for s in ReportingHierarchyTable.scan() if s.get('ManagerID') == eid]
            if employee_id != eid and employee_id not in subs:
                messages.error(request, "Access denied. Employee is not in your line management structure.")
                return redirect('feedback_hub')

        try:
            cycle = FeedbackCyclesTable.get_item({'CycleID': cycle_id})
            if not cycle or cycle.get('Status') == 'Draft':
                raise Http404("Report not ready or cycle not found.")
                
            # HR check on cycle status
            if role == 'Employee' and cycle.get('Status') != 'Published':
                messages.error(request, "Your report has not been published yet.")
                return redirect('feedback_hub')

            # Fetch target employee details
            employee = next((e for e in EmployeesTable.scan() if e.get('EmployeeID') == employee_id), None)
            
            # Fetch all assignments and responses for this employee in this cycle
            assignments = [a for a in FeedbackReviewAssignmentsTable.scan() 
                           if a.get('CycleID') == cycle_id and a.get('RevieweeID') == employee_id]
            
            responses = [r for r in FeedbackReviewResponsesTable.scan() 
                         if r.get('CycleID') == cycle_id and r.get('RevieweeID') == employee_id]
                         
            # Map answers to competencies & calculate scores
            template = FeedbackTemplatesTable.get_item({'TemplateID': cycle.get('TemplateID')})
            competency_list = [c for c in FeedbackCompetenciesTable.scan() if c.get('CompetencyID') in template.get('Competencies', [])]
            questions = [q for q in FeedbackQuestionsTable.scan() if q.get('QuestionID') in template.get('Questions', [])]
            
            # Scoring & aggregation calculations
            scores_by_relationship = {} # relationship -> competency -> list of ratings
            comments = []
            
            weightages = cycle.get('Weightages', {})
            
            for r in responses:
                # Find relationship from assignment
                assign = next((a for a in assignments if a.get('ReviewerID') == r.get('ReviewerID')), None)
                if not assign:
                    continue
                rel = assign.get('Relationship', 'Peer')
                
                if rel not in scores_by_relationship:
                    scores_by_relationship[rel] = {}
                    
                # Add comments (anonymization check)
                is_self = rel == 'Self'
                is_manager = rel == 'Manager'
                
                show_reviewer_details = not cycle.get('Anonymous') or is_self or is_manager
                
                if r.get('Comments'):
                    comments.append({
                        'Text': r.get('Comments'),
                        'Role': assign.get('ReviewerRole', 'Colleague') if show_reviewer_details else 'Anonymous Colleague',
                        'Relationship': rel if show_reviewer_details else 'Peer/Direct Report'
                    })
                    
                # Map answers
                for q_id, val in r.get('Answers', {}).items():
                    # Check if val is numerical rating
                    try:
                        numeric_val = float(val)
                    except ValueError:
                        continue # Skip non-numerical replies
                        
                    q_obj = next((q for q in questions if q.get('QuestionID') == q_id), None)
                    if not q_obj:
                        continue
                        
                    comp_name = q_obj.get('Category', 'Other')
                    if comp_name not in scores_by_relationship[rel]:
                        scores_by_relationship[rel][comp_name] = []
                    scores_by_relationship[rel][comp_name].append(numeric_val)

            # Compute competency aggregates
            comp_scores = {}
            overall_total = 0.0
            overall_weight_sum = 0.0
            
            for comp in competency_list:
                comp_name = comp.get('Name')
                comp_scores[comp_name] = {}
                weighted_rating_sum = 0.0
                rel_weight_sum = 0.0
                
                for rel, comps in scores_by_relationship.items():
                    if comp_name in comps and comps[comp_name]:
                        avg_val = sum(comps[comp_name]) / len(comps[comp_name])
                        comp_scores[comp_name][rel] = round(avg_val, 2)
                        
                        # Apply weights
                        w = float(weightages.get(rel, 0))
                        weighted_rating_sum += avg_val * (w / 100.0)
                        rel_weight_sum += (w / 100.0)
                        
                if rel_weight_sum > 0:
                    final_comp_score = round(weighted_rating_sum / rel_weight_sum, 2)
                    comp_scores[comp_name]['Weighted'] = final_comp_score
                    overall_total += final_comp_score * float(comp.get('Weight', 10))
                    overall_weight_sum += float(comp.get('Weight', 10))
                    
            final_overall_score = round(overall_total / overall_weight_sum, 2) if overall_weight_sum > 0 else 0.0

            # Development Plan
            plans = FeedbackDevelopmentPlansTable.scan()
            plan = next((p for p in plans if p.get('CycleID') == cycle_id and p.get('EmployeeID') == employee_id), None)

            # Add to context
            log_feedback_action(request, 'VIEW_REPORT', f"Viewed 360 report for: {employee_id}")
            return render(request, 'core/feedback360/report_card.html', {
                'cycle': cycle,
                'employee': employee,
                'comp_scores': comp_scores,
                'overall_score': final_overall_score,
                'comments': comments,
                'plan': plan,
                'competency_list': competency_list,
                'relationship_types': list(scores_by_relationship.keys())
            })
        except Exception as e:
            messages.error(request, f"Error rendering feedback report: {e}")
            return redirect('feedback_hub')

# Acknowledge Report & Plan Creation
class AcknowledgeReportView(LoginRequiredMixin, View):
    def post(self, request, cycle_id):
        eid = request.user.employee_id
        try:
            # Check for existing plan/report tracking
            plans = FeedbackDevelopmentPlansTable.scan()
            plan = next((p for p in plans if p.get('CycleID') == cycle_id and p.get('EmployeeID') == eid), None)
            
            if not plan:
                pid = str(uuid.uuid4())
                plan = {
                    'PlanID': pid,
                    'OrgID': request.user.org_id,
                    'CycleID': cycle_id,
                    'EmployeeID': eid,
                    'Goals': []
                }
                
            plan['EmployeeAcknowledged'] = True
            plan['AcknowledgedAt'] = get_local_now().isoformat()
            
            FeedbackDevelopmentPlansTable.put_item(plan)
            log_feedback_action(request, 'ACKNOWLEDGE_REPORT', f"Employee {eid} acknowledged report for cycle {cycle_id}")
            return JsonResponse({'success': True, 'message': 'Report acknowledged successfully.'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})

# Create Manager Development Plan Goals
class CreateDevelopmentPlanView(LoginRequiredMixin, View):
    def post(self, request, cycle_id, employee_id):
        if request.user.role != 'Manager':
            messages.error(request, "Only direct managers can author development plans.")
            return redirect('feedback_hub')
            
        action_item = request.POST.get('action_item', '').strip()
        timeline = request.POST.get('timeline', '').strip()
        support = request.POST.get('support_needed', '').strip()
        
        if not action_item:
            messages.error(request, "Development goals require an action item.")
            return redirect('feedback_report', cycle_id=cycle_id, employee_id=employee_id)
            
        try:
            plans = FeedbackDevelopmentPlansTable.scan()
            plan = next((p for p in plans if p.get('CycleID') == cycle_id and p.get('EmployeeID') == employee_id), None)
            
            if not plan:
                pid = str(uuid.uuid4())
                plan = {
                    'PlanID': pid,
                    'OrgID': request.user.org_id,
                    'CycleID': cycle_id,
                    'EmployeeID': employee_id,
                    'Goals': [],
                    'EmployeeAcknowledged': False
                }
                
            # Append new goal
            goal_rec = {
                'GoalID': str(uuid.uuid4()),
                'ActionItem': action_item,
                'Timeline': timeline,
                'SupportNeeded': support,
                'CreatedAt': get_local_now().isoformat()
            }
            plan['Goals'].append(goal_rec)
            plan['ManagerSignOff'] = True
            
            FeedbackDevelopmentPlansTable.put_item(plan)
            log_feedback_action(request, 'CREATE_DEVELOPMENT_GOAL', f"Added development goal for employee {employee_id}")
            messages.success(request, "Development goal added successfully to report card.")
        except Exception as e:
            messages.error(request, f"Error saving plan goal: {e}")
            
        return redirect('feedback_report', cycle_id=cycle_id, employee_id=employee_id)

# Audit Log Page
class FeedbackAuditLogsView(LoginRequiredMixin, View):
    def get(self, request):
        if request.user.role not in ('Super admin', 'HR ADMIN'):
            messages.error(request, "Access denied.")
            return redirect('feedback_hub')
            
        org_id = request.user.org_id
        logs = [l for l in FeedbackAuditLogsTable.scan() if l.get('OrgID') == org_id or request.user.role == 'Super admin']
        
        # Sort by timestamp descending
        logs = sorted(logs, key=lambda x: x.get('Timestamp', ''), reverse=True)
        return render(request, 'core/feedback360/audit_logs.html', {
            'logs': logs
        })
