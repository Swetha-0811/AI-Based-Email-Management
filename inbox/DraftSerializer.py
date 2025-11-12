@api_view(['GET'])
def drafts_view(request):
    page_number = request.GET.get('page', 1)
    per_page = request.GET.get('per_page', 10)
    refresh = request.GET.get('refresh', 'false').lower() == 'true'  # New refresh parameter
    
    try:
        page_number = int(page_number)
        if page_number < 1:
            page_number = 1
    except ValueError:
        page_number = 1
        
    try:
        per_page = int(per_page)
        if per_page < 1:
            per_page = 10
        if per_page > 50:
            per_page = 50
    except ValueError:
        per_page = 10
        
    try:
        user = request.user if request.user.is_authenticated else None
        service = get_gmail_service(user=user)
        
        if not service:
            return Response({
                'ok': False, 
                'error': 'Authentication required. Please connect your Gmail account.',
                'auth_required': True
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        # Get authenticated email for verification
        try:
            profile = service.users().getProfile(userId='me').execute()
            authenticated_email = profile.get('emailAddress')
            logger.info(f"Fetching drafts for authenticated Gmail account: {authenticated_email}")
        except Exception as e:
            logger.error(f"Error getting Gmail profile: {str(e)}")
            authenticated_email = "Unknown"
        
        # Clear cache if refresh requested
        if refresh:
            cache_key = f"gmail_drafts_{per_page}"
            cache.delete(cache_key)
            logger.info(f"Cleared drafts cache on refresh request")
        
        # Fetch drafts from Gmail
        drafts = fetch_drafts(service, max_results=100)
        
        if not drafts:
            logger.warning("No drafts returned from fetch_drafts")
            # Try to get more debug information
            try:
                debug_response = service.users().drafts().list(userId='me', maxResults=1).execute()
                logger.info(f"Debug drafts response: {debug_response}")
            except Exception as debug_error:
                logger.error(f"Debug error: {str(debug_error)}")
            
            return Response({
                'ok': True, 
                'drafts': [], 
                'total_pages': 0, 
                'current_page': 1,
                'authenticated_email': authenticated_email,
                'debug_info': "No drafts found. Check logs for details."
            })
        
        # Add category and priority information if user is authenticated
        if user and user.is_authenticated:
            for draft in drafts:
                # Add category information
                category = CategorizationService.get_email_category(user, draft['id'])
                if category:
                    draft['category'] = category.category
                else:
                    draft['category'] = ''
                
                # Add priority information
                priority = PriorityScoringService.get_email_priority(user, draft['id'])
                if priority:
                    draft['priority'] = priority.priority
                else:
                    draft['priority'] = 0
        
        # Use DraftSerializer instead of EmailSerializer
        paginator = Paginator(drafts, per_page)
        try:
            page_obj = paginator.page(page_number)
        except EmptyPage:
            logger.warning(f"Requested page {page_number} out of range. Returning last page.")
            page_obj = paginator.page(paginator.num_pages)
        
        # Use DraftSerializer for drafts
        from .serializers import DraftSerializer
        serializer = DraftSerializer(page_obj.object_list, many=True)
        
        return Response({
            'ok': True,
            'drafts': serializer.data,
            'total_pages': paginator.num_pages,
            'current_page': page_obj.number,
            'per_page': per_page,
            'total_drafts': len(drafts),
            'has_next': page_obj.has_next(),
            'has_previous': page_obj.has_previous(),
            'authenticated_email': authenticated_email
        })
    except Exception as e:
        logger.error(f"Error in drafts_view: {str(e)}", exc_info=True)
        error_msg = "Failed to fetch drafts"
        
        if "rateLimitExceeded" in str(e):
            error_msg = "Gmail API rate limit exceeded. Please try again later."
        elif "invalid_grant" in str(e):
            error_msg = "Authentication expired. Please reconnect your Gmail account."
        
        return Response({
            'ok': False, 
            'error': error_msg,
            'auth_required': "invalid_grant" in str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)