#include "TaskPointActor.h"

#include "ue5project/Interaction/UserInterface/SpaceWidget/TagWidget.h"

ATaskPointActor::ATaskPointActor()
{
	PrimaryActorTick.bCanEverTick = false;
}

void ATaskPointActor::InitTaskPoint(const FTaskPointInfo& InTaskPointInfo)
{
	TaskPointInfo = InTaskPointInfo;
	if (TagWidget.IsValid())
	{
		TagWidget->SetWidgetType(STagWidget::EWidgetType::TaskPoint);
	}
}

FString ATaskPointActor::GetTaskPointId() const
{
	return TaskPointInfo.TaskPointId;
}

void ATaskPointActor::BeginPlay()
{
	Super::BeginPlay();
}
